"""Exercise real settings Lua/LVGL via an explicitly supplied Q2-SoC Windows runner."""

from pathlib import Path
import argparse
import hashlib
import struct
import subprocess
import tempfile
from q2app import pack

ROOT = Path(__file__).resolve().parents[1]


def pixel(path, x, y):
    """Read one RGB pixel from the runner's uncompressed 32-bit BMP capture."""
    data = path.read_bytes()
    offset = struct.unpack_from("<I", data, 10)[0]
    width, height = struct.unpack_from("<ii", data, 18)
    row = height - 1 - y if height > 0 else y
    return struct.unpack_from("<I", data, offset + (row * width + x) * 4)[0] & 0xFFFFFF


def check(runner, status_bar_height=0):
    """Use temporary package copies and media; never overwrite a user's saved preferences."""
    with tempfile.TemporaryDirectory(prefix="q2-settings-") as directory:
        work = Path(directory)
        for name in ("settings", "ui-demo"):
            pack(ROOT / "apps" / name, work / f"{name}.q2app")
        media = work / "preferences.lfs"

        def run(
            name="settings", clicks=(), size=(502, 410), grant=True, storage=media, expected=0, error=None
        ):
            staged = work / f"{name}.run"
            capture = work / "frame.bmp"
            args = [
                str(runner),
                str(staged / "manifest.json"),
                str(staged / "main.lua"),
                "--grant",
                "system.info",
                "--grant",
                "display.ui",
                "--headless",
                "--frames",
                "30",
                "--width",
                str(size[0]),
                "--height",
                str(size[1]),
                "--capture",
                str(capture),
            ]
            if storage:
                args += ["--storage-file", str(storage)]
            if grant:
                args += ["--grant", "storage.private"]
            for x, y in clicks:
                args += ["--click", str(x), str(y + status_bar_height)]
            p = subprocess.run(args, capture_output=True, text=True, timeout=30)
            assert p.returncode == expected, p.stdout + p.stderr
            if error:
                assert error in p.stderr and "non-string Lua error" not in p.stderr, p.stderr
            return capture

        baseline = pixel(run(), 490, 400)
        assert baseline not in (0x111827, 0x20382C)
        # Click the real settings entry, then the real Midnight button; restart in a new process.
        assert pixel(run(clicks=((80, 108), (80, 172))), 490, 400) == 0x111827
        assert pixel(run(), 490, 400) == 0x111827
        assert pixel(run(clicks=((80, 108), (80, 236))), 490, 400) == 0x20382C
        assert pixel(run(), 490, 400) == 0x20382C
        assert pixel(run(clicks=((80, 108), (80, 108))), 490, 400) == baseline
        # Missing grant allows an honest session-only preview and never changes persisted selection.
        before = hashlib.sha256(media.read_bytes()).digest()
        assert pixel(run(clicks=((80, 108), (80, 172)), grant=False), 490, 400) == 0x111827
        assert hashlib.sha256(media.read_bytes()).digest() == before
        assert pixel(run(), 490, 400) == baseline
        for name in ("settings", "ui-demo"):
            for size in ((502, 410), (410, 502), (320, 480), (64, 64)):
                run(name, size=size)
        bad = work / "existing-invalid.lfs"
        bad.write_bytes(b"do not format existing media")
        run(storage=bad, expected=1)
        assert bad.read_bytes() == b"do not format existing media"
        source = work / "settings.run/main.lua"
        original = source.read_bytes()
        source.write_text("local q=require('q2'); assert(q.ui.label(0,q.ui.height(),'outside')); return {}")
        run(expected=1, error="invalid_argument")
        source.write_bytes(original)
        # Header is still PNG-shaped; CRC/decode errors must fail boot rather than pretend to render.
        asset = work / "settings.run/assets/home-background.png"
        data = bytearray(asset.read_bytes())
        data[29] ^= 1
        asset.write_bytes(data)
        run(expected=1)
        print(
            "PASS: settings images, real clicks, persistence, denied storage, 4 resolutions, corrupt media/PNG"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--status-bar-height", type=int, default=0)
    args = parser.parse_args()
    check(args.runner.resolve(), args.status_bar_height)
