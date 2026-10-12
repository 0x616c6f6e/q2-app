"""Real HTTP + Lua + LVGL cover tests using generated, noncopyrighted PNG/JPEG images."""

import argparse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from PIL import Image


def picture(color, format="PNG", size=(64, 64), **options):
    stream = io.BytesIO()
    Image.new("RGB", size, color).save(stream, format=format, **options)
    return stream.getvalue()


RED, BLUE, GREEN = (220, 40, 30), (30, 50, 220), (25, 180, 50)
BODIES = {
    "/red.png": picture(RED),
    "/blue.jpg": picture(BLUE, "JPEG"),
    "/progressive.jpg": picture(RED, "JPEG", progressive=True),
    "/large.png": picture(RED, size=(1024, 1024)),
    "/invalid.png": b"not a picture",
    "/oversize": b"x" * 262145,
}


class Handler(BaseHTTPRequestHandler):
    requests = Counter()

    def log_message(self, *args):
        pass

    def do_GET(self):
        Handler.requests[self.path] += 1
        data = BODIES.get(self.path, BODIES["/red.png"])
        if self.path == "/slow.png":
            time.sleep(1.5)
        if self.path == "/timeout.png":
            time.sleep(5.8)
        self.send_response(404 if self.path == "/404" else 200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


SCRIPT = """local q=require("q2")
local ticks=0
local url=URL
local function render()
    assert(q.ui.clear())
    assert(q.ui.background(0x101c19))
    local label=assert(q.ui.label(20,8,"Cover download test"))
    local ok,err=q.ui.image_url(label,url)
    assert(ok==nil and err.code=="not_found")
    local id=assert(q.ui.image(20,40,"assets/fallback.png",120))
    q.ui.image_url(id,url)
end
return {on_start=render,on_tick=function()
    ticks=ticks+1
    ACTION
    if ticks % 10 == 0 then render() end
end}
"""


def check(runner, output, live_url=None):
    output.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="q2-cover-") as folder:
            work = Path(folder)
            (work / "assets").mkdir()
            (work / "assets/fallback.png").write_bytes(picture(GREEN))
            manifest = {
                "format": 2,
                "id": "2d7f3e18-b368-43e7-9698-eb29015fc1f8",
                "name": "Cover test",
                "version": "1.0.0",
                "entry": "main.lua",
                "type": "app",
                "api": 2,
                "capabilities": {"required": ["display.ui"], "optional": ["network.http"]},
                "resources": {"lua_heap_kib": 64},
            }
            (work / "manifest.json").write_text(json.dumps(manifest), encoding="utf8")
            base = f"http://127.0.0.1:{server.server_port}"

            def run(name, path, color, action="", permission=True, frames=150, url=None):
                Handler.requests.clear()
                script = SCRIPT.replace("URL", json.dumps(url or base + path)).replace("ACTION", action)
                (work / "main.lua").write_text(script, encoding="utf8")
                args = [
                    str(runner),
                    str(work / "manifest.json"),
                    str(work / "main.lua"),
                    "--headless",
                    "--frames",
                    str(frames),
                    "--width",
                    "502",
                    "--height",
                    "410",
                    "--grant",
                    "display.ui",
                    "--capture",
                    str(work / "frame.bmp"),
                ]
                if permission:
                    args += ["--grant", "network.http"]
                result = subprocess.run(args, capture_output=True, text=True, timeout=20)
                logs = result.stdout + result.stderr
                assert result.returncode == 0 and "failed result=" not in logs, logs
                image = Image.open(work / "frame.bmp").convert("RGB")
                if color:
                    pixel = image.getpixel((80, 130))
                    assert max(abs(a - b) for a, b in zip(pixel, color)) <= 3, (name, pixel, color, logs)
                image.save(output / (name + ".png"))
                (output / (name + ".log")).write_text(logs, encoding="utf8")
                print("PASS: cover " + name, flush=True)
                return logs, dict(Handler.requests)

            logs, calls = run("png-cache", "/red.png", RED)
            assert calls == {"/red.png": 1} and "remote image ready" in logs
            run("jpeg-cache", "/blue.jpg", BLUE)
            for path in ("/invalid.png", "/progressive.jpg", "/large.png", "/oversize", "/404"):
                logs, calls = run("fallback-" + path[1:], path, GREEN)
                assert "remote image fallback" in logs and calls == {path: 1}
            logs, calls = run("permission-denied", "/red.png", GREEN, permission=False)
            assert not calls
            action = "if ticks == 10 then url=" + json.dumps(base + "/blue.jpg") + " end"
            logs, calls = run("skip-cancels-old", "/slow.png", BLUE, action)
            assert calls == {"/slow.png": 1, "/blue.jpg": 1}
            logs, calls = run("timeout", "/timeout.png", GREEN, frames=390)
            assert "remote image fallback: timeout" in logs and calls == {"/timeout.png": 1}
            run("exit-pending", "/slow.png", (17, 24, 39), "if ticks == 10 then q.os.exit() end")
            if live_url:
                logs, _ = run("live-cdn", "", None, frames=360, url=live_url)
                assert "remote image ready 256x256" in logs, logs
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--live-url-file", type=Path)
    args = parser.parse_args()
    live = args.live_url_file.read_text(encoding="utf8").strip() if args.live_url_file else None
    check(args.runner.resolve(), args.artifacts.resolve(), live)
