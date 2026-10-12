"""Exercise managed Home navigation using the real Lua/LVGL Windows runner."""

from pathlib import Path
import argparse
import json
import subprocess
import tempfile
from q2app import pack_factory
from test_settings_ui import pixel

ROOT = Path(__file__).resolve().parents[1]
GRANTS = (
    "system.info",
    "display.ui",
    "display.text",
    "storage.private",
    "apps.list",
    "apps.launch",
    "apps.navigate",
    "appearance.read",
    "appearance.write",
    "input.keys",
    "system.ui.read",
    "system.lifecycle",
    "data.read",
    "power.read",
    "wireless.read",
    "clock.read",
    "system.settings",
)


def check(runner, status_bar_height=0):
    """Test staged packages and temporary media, preserving all user preferences."""
    # APP positions are viewport-relative; injected pointer coordinates are physical.
    bar = status_bar_height
    center = bar + int((410 - bar) * 0.43)
    small_center = bar + int((320 - bar) * 0.43)
    with tempfile.TemporaryDirectory(prefix="q2-home-") as directory:
        work = Path(directory)
        catalog = pack_factory(ROOT, work)
        entries = catalog["apps"]
        home = next(x for x in entries if x["directory"] == "homepage")
        media = work / "preferences.lfs"

        def run(clicks=(), size=(502, 410), initial="homepage", expected=0):
            paths = lambda name: [str(work / (name + ".run") / p) for p in ("manifest.json", "main.lua")]
            args = [
                str(runner),
                *paths(initial),
                "--home",
                home["id"],
                "--headless",
                "--frames",
                "60",
                "--width",
                str(size[0]),
                "--height",
                str(size[1]),
                "--storage-file",
                str(media),
                "--capture",
                str(work / "frame.bmp"),
            ]
            for entry in entries:
                if entry["directory"] == initial:
                    if entry["factory"]:
                        args += ["--initial-factory"]
                else:
                    args += ["--factory-app" if entry["factory"] else "--app", *paths(entry["directory"])]
            for cap in GRANTS:
                args += ["--grant", cap]
            for x, y in clicks:
                args += ["--click", str(x), str(y)]
            p = subprocess.run(args, capture_output=True, text=True, timeout=30)
            logs = p.stdout + p.stderr
            assert p.returncode == expected, logs
            return logs

        logs = run()
        assert "foreground Homepage" in logs, logs
        logs = run(((251, center), (80, 108 + bar), (80, 172 + bar), (430, 36 + bar)))
        assert "foreground System settings" in logs or "foreground System Settings" in logs, logs
        assert logs.count("foreground Homepage") == 2, logs
        assert pixel(work / "frame.bmp", 490, 400) == 0x111827
        run()
        assert pixel(work / "frame.bmp", 490, 400) == 0x111827
        for initial, click in [("ui-demo", (60, 320)), ("device-info", (60, 160 + bar))]:
            logs = run((click,), initial=initial)
            assert "foreground Homepage" in logs, logs
        logs = run(((251, center), (430, 36 + bar)) * 4)
        assert logs.count("foreground Homepage") == 5, logs
        for size in ((410, 502), (320, 480), (64, 64)):
            run(size=size)
        # Left wraps to the final APP; right advances one APP without launching it.
        logs = run(((48, center), (251, center), (36, 24 + bar)))
        assert "foreground Music" in logs and logs.count("foreground Homepage") == 2, logs
        logs = run(((454, center), (251, center), (60, 320)))
        assert "foreground Q2 UI Demo" in logs and logs.count("foreground Homepage") == 2, logs
        # Right wraps at the end, then Left returns to the final APP on a smaller screen.
        logs = run(
            [(282, small_center)] * (len(entries) - 1) + [(38, small_center), (160, small_center), (36, 284)],
            size=(320, 320),
        )
        assert "foreground Music" in logs and logs.count("foreground Homepage") == 2, logs
        # A damaged third-party icon cannot prevent the factory launcher from rendering.
        icon = work / "settings.run/assets/system-settings-icon.png"
        icon_bytes = icon.read_bytes()
        icon.write_bytes(b"invalid PNG")
        assert "foreground Homepage" in run()
        icon.write_bytes(icon_bytes)
        # Initial code failure and later event failure both recover once to Home.
        source = work / "ui-demo.run/main.lua"
        original = source.read_bytes()
        source.write_text("error('intentional startup fault')")
        logs = run(initial="ui-demo")
        assert "Cannot open" in logs and "foreground Homepage" in logs, logs
        # A real registered UI button is necessary to generate a targeted event.
        source.write_text(
            "local q=require('q2'); return {on_start=function() assert(q.ui.button(20,20,'Fault')) end,on_event=function() error('event fault') end}"
        )
        logs = run(((50, 40 + bar),), initial="ui-demo")
        assert "event fault" in logs and "foreground Homepage" in logs, logs
        source.write_bytes(original)
        # Non-factory packages cannot modify system appearance even if capability was granted.
        manifest = work / "ui-demo.run/manifest.json"
        data = json.loads(manifest.read_text())
        data["capabilities"]["optional"].append("appearance.write")
        manifest.write_text(json.dumps(data))
        source.write_text(
            "local q=require('q2'); return {on_start=function() local v,e=q.appearance.set('forest'); assert(v==nil and e.code=='permission_denied'); q.os.exit() end}"
        )
        logs = run(initial="ui-demo")
        assert "failed result=" not in logs and "foreground Homepage" in logs, logs
        assert pixel(work / "frame.bmp", 490, 400) == 0x111827
        # Failure of Home is fatal, not an endless restart loop.
        (work / "homepage.run/main.lua").write_text("error('home fault')")
        logs = run(expected=1)
        assert "home fault" in logs and logs.count("APP ") < 5, logs
        print(
            "PASS: Home default, icons, launch/return, shared wallpaper persistence, single-app arrows and wraparound, icon fallback, repeated switching, fault fallback, factory permission"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--status-bar-height", type=int, default=0)
    args = parser.parse_args()
    check(args.runner.resolve(), args.status_bar_height)
