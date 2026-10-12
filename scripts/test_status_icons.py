"""Verify status artwork through real Home Lua, LVGL captures and Web device updates."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request
from PIL import Image, ImageChops
from q2app import pack_factory
from test_lifecycle_ui import GRANTS

ROOT = Path(__file__).resolve().parents[1]


def check(runner, artifacts):
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="q2-status-icons-") as directory:
        work = Path(directory)
        catalog = pack_factory(ROOT, work)["apps"]
        home = next(x for x in catalog if x["directory"] == "homepage")
        cases = [
            ("strong-charging", -45, True, 50, True, "wifi-strong", "ble-connected", "battery-charging-50"),
            ("medium", -65, False, 75, False, "wifi-medium", "ble-idle", "battery-75"),
            ("weak-empty", -85, True, 0, False, "wifi-weak", "ble-connected", "battery-0"),
            ("disconnected-full", None, False, 100, False, "wifi-disconnected", "ble-idle", "battery-100"),
        ]
        for name, rssi, ble, percent, charging, *expected in cases:
            # Settings foreground proves its content cannot overwrite resident status icons.
            initial = "settings" if name == "medium" else "homepage"

            def paths(app):
                return [str(work / (app + ".run") / f) for f in ("manifest.json", "main.lua")]

            capture = work / (name + ".bmp")
            args = [
                str(runner),
                *paths(initial),
                "--home",
                home["id"],
                "--initial-factory",
                "--headless",
                "--frames",
                "160",
                "--width",
                "502",
                "--height",
                "410",
                "--web-port",
                "0",
                "--storage-file",
                str(work / (name + ".lfs")),
                "--capture",
                str(capture),
            ]
            for entry in catalog:
                if entry["directory"] != initial:
                    args += ["--factory-app" if entry["factory"] else "--app", *paths(entry["directory"])]
            for grant in GRANTS:
                args += ["--grant", grant]
            log = work / (name + ".log")
            with log.open("w") as output:
                process = subprocess.Popen(args, stdout=output, stderr=output)
                try:
                    deadline = time.monotonic() + 8
                    match = None
                    while time.monotonic() < deadline:
                        match = re.search(r"http://127\.0\.0\.1:\d+/", log.read_text())
                        if match:
                            break
                        assert process.poll() is None, log.read_text()
                        time.sleep(0.03)
                    assert match, log.read_text()
                    url = match[0].rstrip("/")
                    with urllib.request.urlopen(url + "/api/state", timeout=3) as response:
                        token = json.load(response)["token"]
                    queries = [
                        f"group=wifi&mode=value&connected={int(rssi is not None)}&rssi_dbm={rssi or -65}",
                        f"group=ble&mode=value&connected={int(ble)}&rssi_dbm=-65",
                        f"group=battery&mode=value&percent={percent}&voltage_mv=3900&charging={int(charging)}",
                    ]
                    for query in queries:
                        req = urllib.request.Request(
                            url + "/api/device?" + query, method="POST", headers={"X-Q2-Token": token}
                        )
                        with urllib.request.urlopen(req, timeout=3) as response:
                            assert response.status == 200
                    assert process.wait(timeout=15) == 0, log.read_text()
                finally:
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=5)
            assert "failed result=" not in log.read_text(), log.read_text()
            actual = Image.open(capture).convert("RGB")
            actual.save(artifacts / (name + ".png"))
            for x, asset in zip((351, 380, 409), expected):
                icon = Image.open(ROOT / "apps/homepage/assets" / ("status-" + asset + ".png")).convert(
                    "RGBA"
                )
                reference = Image.new("RGBA", (24, 24), (11, 16, 24, 255))
                reference.alpha_composite(icon)
                difference = ImageChops.difference(actual.crop((x, 4, x + 24, 28)), reference.convert("RGB"))
                assert max(high for low, high in difference.getextrema()) <= 3, (name, asset)
            print("PASS: status icons " + name, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    args = parser.parse_args()
    check(args.runner.resolve(), args.artifacts.resolve())
