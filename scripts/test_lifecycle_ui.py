"""Real resident Home, independent VMs, scrolling settings, lock routing and renewable saver lease."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request
from q2app import pack_factory
from test_settings_ui import pixel

ROOT = Path(__file__).resolve().parents[1]
GRANTS = [
    "system.info",
    "system.log",
    "display.ui",
    "display.text",
    "input.keys",
    "storage.private",
    "apps.list",
    "apps.launch",
    "apps.navigate",
    "appearance.read",
    "appearance.write",
    "system.ui.read",
    "system.settings",
    "system.lifecycle",
    "data.read",
    "power.read",
    "wireless.read",
    "clock.read",
    "screensaver.inhibit",
]


def check(runner, artifacts=None):
    with tempfile.TemporaryDirectory(prefix="q2-lifecycle-") as directory:
        work = Path(directory)
        catalog = pack_factory(ROOT, work)["apps"]
        home = next(x for x in catalog if x["directory"] == "homepage")
        media = work / "prefs.lfs"

        def arguments(initial="homepage", frames=100, capture=None, actions=(), web=False):
            def paths(name):
                return [str(work / (name + ".run") / f) for f in ("manifest.json", "main.lua")]

            argv = [
                str(runner),
                *paths(initial),
                "--home",
                home["id"],
                "--headless",
                "--frames",
                str(frames),
                "--storage-file",
                str(media),
            ]
            for entry in catalog:
                if entry["directory"] == initial:
                    if entry["factory"]:
                        argv += ["--initial-factory"]
                else:
                    argv += ["--factory-app" if entry["factory"] else "--app", *paths(entry["directory"])]
            for grant in GRANTS:
                argv += ["--grant", grant]
            if capture:
                argv += ["--capture", str(capture)]
            if web:
                argv += ["--web-port", "0"]
            return argv + list(actions)

        def run(name, initial="homepage", actions=(), frames=100):
            capture = work / (name + ".bmp")
            result = subprocess.run(
                arguments(initial, frames, capture, actions), capture_output=True, text=True, timeout=30
            )
            logs = result.stdout + result.stderr
            assert result.returncode == 0, logs
            assert "failed result=" not in logs, logs
            if artifacts:
                artifacts.mkdir(parents=True, exist_ok=True)
                from PIL import Image

                Image.open(capture).save(artifacts / (name + ".png"))
            return logs, capture

        _, capture = run("home")
        assert pixel(capture, 0, 0) == 0x0B1018
        logs, top = run("settings-top", initial="settings")
        assert "foreground Homepage" in logs and "foreground System settings" in logs
        _, bottom = run("settings-scrolled", initial="settings", actions=("--scroll-down", "470"))
        assert top.read_bytes() != bottom.read_bytes()
        assert pixel(bottom, 0, 0) == 0x0B1018
        # Toggle status bar using a real settings button and verify saved override on restart.
        _, off = run("bar-off", initial="settings", actions=("--click", "120", "200"))
        assert pixel(off, 0, 0) != 0x0B1018
        _, off = run("bar-off-restart")
        assert pixel(off, 0, 0) != 0x0B1018
        run("bar-restored", initial="settings", actions=("--click", "120", "170"))
        # Settings exits; resident Home instance must not start a second time.
        logs, _ = run("home-return", actions=("--click", "251", "194", "--click", "440", "60"))
        assert logs.count("APP " + home["id"] + " started instance=") == 1, logs
        assert "foreground Homepage (resumed)" in logs, logs
        for w, h in ((410, 502), (320, 320), (64, 64)):
            result = subprocess.run(
                arguments() + ["--width", str(w), "--height", str(h)],
                capture_output=True,
                text=True,
                timeout=20,
            )
            assert result.returncode == 0, result.stdout + result.stderr
        # An ordinary VM keeps ticking and modifying only its own hidden widgets after Home is shown.
        source = work / "ui-demo.run/main.lua"
        original = source.read_bytes()
        source.write_text(
            """local q=require('q2');local label,n;return {
          on_start=function() label=assert(q.ui.label(10,10,'Background'));n=0;assert(q.apps.home()) end,
          on_tick=function() n=n+1;assert(q.ui.set_text(label,'tick '..n));
            if n==60 then assert(q.os.log('info','BACKGROUND_TICK_60')) end end}
        """
        )
        manifest_path = work / "ui-demo.run/manifest.json"
        manifest_original = manifest_path.read_bytes()
        manifest = json.loads(manifest_original)
        manifest["capabilities"]["optional"].append("system.log")
        manifest_path.write_text(json.dumps(manifest))
        logs, _ = run(
            "three-vms", initial="ui-demo", actions=("--click", "454", "194", "--click", "251", "194")
        )
        assert "BACKGROUND_TICK_60" in logs and "foreground System settings" in logs, logs
        assert logs.count(" started instance=") == 3, logs
        source.write_bytes(original)
        manifest_path.write_bytes(manifest_original)
        print(
            "PASS: resident Home, three concurrent VMs, isolated UI, scroll and persistent settings",
            flush=True,
        )

        # Trusted temporary factory setup changes only this test's temporary preferences.
        probe = next(x for x in catalog if x["directory"] == "key-demo")
        settings_manifest_path = work / "settings.run/manifest.json"
        setup_manifest = json.loads(settings_manifest_path.read_text())
        setup_manifest["capabilities"]["optional"].append("apps.launch")
        settings_manifest_path.write_text(json.dumps(setup_manifest))
        (work / "settings.run/main.lua").write_text(
            """local q=require('q2');return {on_start=function()
          assert(q.shell.set('status_bar',true));assert(q.shell.set('screensaver',true));
          assert(q.shell.set('idle_timeout_ms',1000));assert(q.shell.set('clock_move_interval_ms',1000));
          assert(q.shell.set('lock_enabled',true));assert(q.shell.set('unlock_key','POWER'));
          assert(q.shell.set('unlock_action',2));assert(q.apps.launch('"""
            + probe["id"]
            + """')) end}"""
        )
        probe_manifest = work / "key-demo.run/manifest.json"
        manifest = json.loads(probe_manifest.read_text())
        manifest["capabilities"]["optional"] = [
            "system.log",
            "system.info",
            "apps.navigate",
            "apps.list",
            "system.ui.read",
            "screensaver.inhibit",
            "system.settings",
            "system.lifecycle",
            "data.read",
            "power.read",
            "wireless.read",
            "clock.read",
        ]
        probe_manifest.write_text(json.dumps(manifest))
        (work / "key-demo.run/main.lua").write_text(
            """local q=require('q2');local total=0;local inhibit=false;
          local denied=false;return {on_start=function()
            assert(q.keys.watch(true));for _,name in ipairs({'POWER','PLAY','NEXT','BACK'}) do
            assert(q.data.subscribe('input.key.'..name..'.action')) end;assert(q.ui.background(0x123456));assert(q.ui.label(16,64,'Lyrics preview'));
            local v,e=q.shell.layer('status');assert(v==nil and e.code=='permission_denied');
            v,e=q.shell.set('lock_enabled',false);assert(v==nil and e.code=='permission_denied');
            assert(q.os.log('info','UNTRUSTED_DENIED')) end,
          on_tick=function()
            assert(q.keys.last('POWER')==0);
            if inhibit then local v,e=q.shell.keep_awake();
              if not v then assert(e.code=='permission_denied');
                if not denied then assert(q.os.log('info','BACKGROUND_INHIBIT_DENIED'));denied=true end end end end,
          on_event=function(e) if e.type~='data.event' then return end;
            e.text=string.sub(e.key,11,#e.key-7);
            total=total+1;assert(q.os.log('info','PROBE '..e.text..' '..e.value..' total='..total));
            if e.text=='NEXT' then inhibit=true end;
            if e.text=='BACK' then inhibit=false end;
            if e.text=='PLAY' and e.value==2 then assert(q.apps.home()) end end}
        """
        )
        logfile = work / "web.log"
        with logfile.open("w", encoding="utf8") as output:
            process = subprocess.Popen(
                arguments("settings", 1400, work / "locked.bmp", web=True), stdout=output, stderr=output
            )
            try:
                deadline = time.monotonic() + 8
                url = None
                while time.monotonic() < deadline:
                    logs = logfile.read_text(encoding="utf8")
                    match = re.search(r"http://127\.0\.0\.1:(\d+)/", logs)
                    if match:
                        url = match.group(0).rstrip("/")
                        break
                    assert process.poll() is None, logs
                    time.sleep(0.03)
                assert url, logs
                token = None

                def request(path, post=False):
                    headers = {"X-Q2-Token": token} if post else {}
                    req = urllib.request.Request(
                        url + path, method="POST" if post else "GET", headers=headers
                    )
                    with urllib.request.urlopen(req, timeout=3) as response:
                        return json.load(response)

                token = request("/api/state")["token"]

                def click(name, twice=False):
                    for _ in range(2 if twice else 1):
                        assert request("/api/key?name=" + name + "&state=down", True)["ok"]
                        time.sleep(0.065)
                        assert request("/api/key?name=" + name + "&state=up", True)["ok"]
                        time.sleep(0.04)
                    time.sleep(0.38)

                def wait_locked(wanted):
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline:
                        state = request("/api/state")
                        if state["locked"] == wanted:
                            return state
                        time.sleep(0.05)
                    raise AssertionError(state)

                state = wait_locked(True)
                assert state["lifecycle"] and state["screensaver"]
                click("PLAY")
                click("POWER")
                assert request("/api/state")["locked"]
                assert "PROBE " not in logfile.read_text()
                click("POWER", True)
                wait_locked(False)
                assert "PROBE " not in logfile.read_text(), "Unlock leaked into APP"
                click("NEXT")
                time.sleep(2.2)
                assert not request("/api/state")["screensaver"], logfile.read_text()
                assert "PROBE NEXT 1 total=1" in logfile.read_text()
                click("BACK")
                wait_locked(True)
                click("POWER", True)
                wait_locked(False)
                click("NEXT")
                click("PLAY", True)  # Return Home while keeping custom-saver VM alive.
                wait_locked(True)
                logs = logfile.read_text()
                assert "BACKGROUND_INHIBIT_DENIED" in logs and "UNTRUSTED_DENIED" in logs, logs
                assert logs.count("APP " + home["id"] + " started instance=") == 1, logs
                assert "failed result=" not in logs, logs
                assert process.wait(timeout=25) == 0, logfile.read_text()
                assert pixel(work / "locked.bmp", 0, 0) == 0x0B1018
                assert pixel(work / "locked.bmp", 0, 40) == 0
                if artifacts:
                    from PIL import Image

                    Image.open(work / "locked.bmp").save(artifacts / "locked.png")
                print(
                    "PASS: lock intercepts keys, double POWER unlock consumed, renewable foreground lease, background denied",
                    flush=True,
                )
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)

        # A saved shortcut removed from a future product registry must not strand the user in a lock.
        (work / "key-demo.run/main.lua").write_text(
            """local q=require('q2');return {on_start=function()
              assert(q.shell.get('lock_enabled')==false);
              assert(q.os.log('info','MISSING_UNLOCK_KEY_SAFE')) end}"""
        )
        logs, _ = run("missing-unlock-key", initial="key-demo", actions=("--key", "BACK"), frames=40)
        assert "MISSING_UNLOCK_KEY_SAFE" in logs, logs
        print("PASS: saved lock disabled when its configured key is no longer registered", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    check(args.runner.resolve(), args.artifacts.resolve() if args.artifacts else None)
