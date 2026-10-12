"""Decode real rendered QR APP frames (requires Pillow and zxing-cpp)."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from PIL import Image
import zxingcpp
from q2app import pack, pack_factory

ROOT = Path(__file__).resolve().parents[1]


def check(runner, artifacts):
    with tempfile.TemporaryDirectory(prefix="q2-qrcode-") as directory:
        work = Path(directory)
        source = work / "source"
        shutil.copytree(ROOT / "apps/qrcode", source)
        original = (source / "main.lua").read_text(encoding="utf8")

        def run(payload, width=502, height=410, clicks=(), name="frame"):
            (source / "main.lua").write_text(
                original.replace('"Q2-Kernel"', json.dumps(payload, ensure_ascii=False)), encoding="utf8"
            )
            pack(source, work / "qrcode.q2app")
            capture = work / (name + ".bmp")
            args = [
                str(runner),
                str(work / "qrcode.run/manifest.json"),
                str(work / "qrcode.run/main.lua"),
                "--grant",
                "display.ui",
                "--headless",
                "--frames",
                "15",
                "--width",
                str(width),
                "--height",
                str(height),
                "--capture",
                str(capture),
            ]
            for x, y in clicks:
                args += ["--click", str(x), str(y)]
            result = subprocess.run(args, capture_output=True, text=True, timeout=20)
            assert result.returncode == 0, result.stdout + result.stderr
            image = Image.open(capture)
            codes = zxingcpp.read_barcodes(image)
            if not clicks:
                assert len(codes) == 1 and codes[0].text == payload, (payload, [c.text for c in codes])
            if artifacts:
                artifacts.mkdir(parents=True, exist_ok=True)
                image.save(artifacts / (name + ".png"))
            return result.stdout + result.stderr

        run("Q2-Kernel", name="landscape")
        run("Q2-Kernel", 410, 502, name="portrait")
        run("Q2-Kernel", 320, 320, name="small")
        run("https://example.com/?a=1&b=2", name="url")
        run("你好，Q2", name="utf8")
        run("x" * 255, name="max-length")
        logs = run("Q2-Kernel", clicks=[(250, 380)], name="back")
        assert "iterations=15" not in logs, "Back did not exit"
        # Product catalog integration: QR is a normal foreground APP beside resident Home.
        catalog = pack_factory(ROOT, work / "factory")["apps"]
        home = next(a for a in catalog if a["directory"] == "homepage")
        qr = work / "factory/qrcode.run"
        args = [
            str(runner),
            str(qr / "manifest.json"),
            str(qr / "main.lua"),
            "--home",
            home["id"],
            "--headless",
            "--frames",
            "15",
        ]
        for item in catalog:
            if item["directory"] != "qrcode":
                package = work / "factory" / (item["directory"] + ".run")
                args += [
                    "--factory-app" if item["factory"] else "--app",
                    str(package / "manifest.json"),
                    str(package / "main.lua"),
                ]
        for cap in [
            "display.ui",
            "input.keys",
            "system.info",
            "apps.list",
            "apps.launch",
            "apps.navigate",
            "appearance.read",
            "appearance.write",
            "system.ui.read",
            "system.lifecycle",
            "system.settings",
            "data.read",
            "clock.read",
            "wireless.read",
            "power.read",
        ]:
            args += ["--grant", cap]
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        logs = result.stdout + result.stderr
        assert result.returncode == 0 and "foreground QR Code" in logs, logs
        assert "failed result=" not in logs
        print(
            "PASS: QR framebuffer decodes at 3 resolutions; URL/UTF-8/255 bytes; Back exit; managed Home launch"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    check(args.runner.resolve(), args.artifacts.resolve() if args.artifacts else None)
