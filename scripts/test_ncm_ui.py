"""Real WinHTTP/Lua/LVGL login/catalog integration against a private deterministic API fixture."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from urllib.parse import urlsplit, parse_qs
from PIL import Image
from q2app import pack
from test_homepage_ui import GRANTS

ROOT = Path(__file__).resolve().parents[1]
COOKIE_SUFFIX = '; escape="quote\\slash"'
COOKIE = "MUSIC_U=" + "t" * (4096 - 8 - len(COOKIE_SUFFIX)) + COOKIE_SUFFIX
assert len(COOKIE) == 4096


class Handler(BaseHTTPRequestHandler):
    mode, checks, requests, cache = "success", 0, [], {}

    def log_message(self, *args):
        pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        assert self.headers.get("Content-Type") == "application/json"
        parsed = urlsplit(self.path)
        assert set(parse_qs(parsed.query)) <= {"timestamp"}
        assert "cookie" not in self.path
        Handler.requests.append((parsed.path, data.get("offset")))
        # Match upstream apicache: URL/cookie headers, not JSON body, select the cached response.
        cache_key = self.path
        self.path = parsed.path
        if cache_key in Handler.cache:
            self.reply(Handler.cache[cache_key])
            return
        signed_in = data.get("cookie") == COOKIE
        result = {"code": 200}
        if self.path == "/login/status":
            result = {
                "data": {
                    "code": 200,
                    "profile": (
                        {"userId": 42, "nickname": "Listener", "vipType": 0}
                        if signed_in and self.mode != "invalid-session"
                        else None
                    ),
                }
            }
        elif self.path == "/login/qr/key":
            result["data"] = {"unikey": "fixture-key"}
        elif self.path == "/login/qr/create":
            result["data"] = {"qrurl": "https://music.163.com/login?codekey=fixture-key"}
        elif self.path == "/login/qr/check":
            Handler.checks += 1
            code = (
                800
                if self.mode == "expired"
                else (
                    801
                    if self.mode in ("waiting", "invalid-session")
                    else (801 if self.checks == 1 else 802 if self.checks == 2 else 803)
                )
            )
            result = {"code": code}
            if code == 803:
                result["cookie"] = COOKIE
        elif not signed_in:
            result = {"code": 301}
        elif self.path == "/user/playlist":
            result["playlist"] = [
                {"id": 100, "specialType": 0, "creator": {"userId": 42}, "trackCount": 8},
                {"id": 101, "specialType": 5, "creator": {"userId": 99}, "trackCount": 8},
                {
                    "id": 102,
                    "specialType": 5,
                    "creator": {"userId": 42},
                    "trackCount": 0 if self.mode == "empty" else 8,
                },
            ]
            if self.mode == "auth-expired":
                result = {"code": 301}
            result["more"] = False
        elif self.path == "/playlist/track/all":
            assert data["id"] == 102, "must identify liked library, not simply first playlist"
            start = data["offset"]
            result["songs"] = [self.track(i) for i in range(start, min(start + 6, 8))]
        elif self.path == "/song/url/v1":
            assert "unblock" not in data
            result["data"] = [
                {
                    "id": data["id"],
                    "url": (
                        None
                        if self.mode == "unavailable"
                        else f"http://127.0.0.1:{self.server.server_port}/audio.mp3"
                    ),
                    "type": "mp3",
                    "freeTrialInfo": None,
                }
            ]
        elif self.path == "/lyric":
            result["lrc"] = {"lyric": "[00:00.00]Original test line\n[00:01.00]Another test line\n"}
        raw = b"not JSON" if self.mode == "malformed" else json.dumps(result).encode()
        if self.mode != "http-error":
            Handler.cache[cache_key] = raw
        self.reply(raw)

    def do_GET(self):
        if self.path.startswith("/cover/"):
            index = int(urlsplit(self.path).path.rsplit("/", 1)[1].split(".")[0])
            color = (40 + index * 20, 130, 210)
            stream = io.BytesIO()
            Image.new("RGB", (256, 256), color).save(stream, format="JPEG")
            self.send_response(200)
            self.send_header("Content-Length", str(len(stream.getvalue())))
            self.end_headers()
            self.wfile.write(stream.getvalue())
            return
        assert self.path == "/audio.mp3"
        # MPEG-1 Layer III, 128 kbps / 44.1 kHz mono, empty granules => generated silence.
        # No downloaded or copyrighted media is used by the decoder/device regression.
        frames = 40 if self.mode == "auto-next" else 1000
        raw = (bytes.fromhex("fffb90c4") + bytes(413)) * frames
        if self.mode == "bad-audio":
            raw = b"not an audio file"
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def reply(self, raw):
        self.send_response(503 if self.mode == "http-error" else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def track(self, i):
        return {
            "id": 1000 + i,
            "name": "Test track " + str(i + 1),
            "ar": [{"name": "Test artist"}],
            "al": {
                "name": "Test album",
                "picUrl": f"http://127.0.0.1:{self.server.server_port}/cover/{i}.jpg",
            },
            "dt": 180000,
        }


def check(runner, artifacts):
    artifacts.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="q2-ncm-") as directory:
            work = Path(directory)
            source = work / "source"
            shutil.copytree(ROOT / "apps/music-player", source)
            config = source / "src/config.lua"
            config.write_text(
                config.read_text()
                .replace("https://ncm-api.0x616c6f6e.icu", f"http://127.0.0.1:{server.server_port}")
                .replace("poll_ms = 3000", "poll_ms = 50")
            )
            pack(source, work / "music.q2app")
            pack(ROOT / "apps/homepage", work / "home.q2app")
            media = work / "session.lfs"

            def run(
                name,
                clicks=(),
                mode="success",
                storage=media,
                permission=True,
                width=502,
                height=410,
                managed=False,
                audio=True,
                frames=300,
            ):
                Handler.mode, Handler.checks, Handler.requests, Handler.cache = mode, 0, [], {}
                args = [
                    str(runner),
                    str(work / "music.run/manifest.json"),
                    str(work / "music.run/main.lua"),
                    "--grant",
                    "display.ui",
                    "--grant",
                    "system.log",
                    "--headless",
                    "--frames",
                    str(frames),
                    "--width",
                    str(width),
                    "--height",
                    str(height),
                    "--capture",
                    str(work / "capture.bmp"),
                ]
                if managed:
                    home = json.loads((work / "home.run/manifest.json").read_text())
                    args += [
                        "--home",
                        home["id"],
                        "--factory-app",
                        str(work / "home.run/manifest.json"),
                        str(work / "home.run/main.lua"),
                    ]
                    for cap in GRANTS:
                        if cap not in ("display.ui", "storage.private"):
                            args += ["--grant", cap]
                if audio:
                    args += ["--grant", "audio.playback"]
                if permission:
                    args += ["--grant", "network.http"]
                if storage:
                    args += ["--grant", "storage.private", "--storage-file", str(storage)]
                # Allow startup POST chain before native clicks (each action occupies five frames).
                for x, y in [(0, 0)] * 24 + list(clicks):
                    args += ["--click", str(x), str(y)]
                result = subprocess.run(args, capture_output=True, text=True, timeout=25)
                logs = result.stdout + result.stderr
                assert result.returncode == 0 and "failed result=" not in logs, logs
                assert COOKIE not in logs
                Image.open(work / "capture.bmp").save(artifacts / (name + ".png"))
                (artifacts / (name + ".log")).write_text(logs, encoding="utf8")
                print("PASS: NCM " + name, flush=True)
                return logs, list(Handler.requests)

            api_path = source / "src/api.lua"
            fixed_api = api_path.read_text()
            api_path.write_text(fixed_api.replace(' .. "?timestamp=" .. now', ""))
            pack(source, work / "music.q2app")
            logs, _ = run("cache-bug-reproduced", storage=None)
            assert "state=qr" in logs and "state=ready" not in logs and Handler.checks == 1
            api_path.write_text(fixed_api)
            pack(source, work / "music.q2app")
            logs, _ = run("managed-cold-login", mode="waiting", storage=work / "managed.lfs", managed=True)
            assert "state=qr" in logs and "foreground Homepage (resumed)" not in logs
            # Close Music exactly when QR authorization starts saving, before any fragment write.
            # The temporary Home driver relaunches only after the APP really exits.
            main_path = source / "main.lua"
            original_main = main_path.read_text()
            main_path.write_text(
                original_main.replace(
                    "        c.tick(now)\n",
                    '        c.tick(now)\n        if c.session_state() == "saving" then action("exit") end\n',
                )
            )
            home_source = work / "home-source"
            shutil.copytree(ROOT / "apps/homepage", home_source)
            home_main = home_source / "main.lua"
            home_main.write_text(
                home_main.read_text()
                .replace('local notice = ""', 'local notice = ""\nlocal relaunched = false')
                .replace(
                    "        local next_background = checked(q.appearance.get())",
                    "        if next_foreground == self_id and not relaunched then\n"
                    "            relaunched = true\n"
                    '            checked(q.apps.launch("0166e1e9-2349-4e01-9301-13275b047e1f"))\n'
                    "        end\n        local next_background = checked(q.appearance.get())",
                )
            )
            pack(source, work / "music.q2app")
            pack(home_source, work / "home.q2app")
            logs, requests = run(
                "exit-during-save", storage=work / "early-exit.lfs", managed=True, frames=450
            )
            assert "foreground Homepage (resumed)" in logs and "session=restored" in logs
            assert sum(path == "/login/qr/key" for path, _ in requests) == 1
            assert sum(path == "/login/status" for path, _ in requests) == 2
            assert "audio=playing" in logs
            main_path.write_text(original_main)
            pack(source, work / "music.q2app")
            pack(ROOT / "apps/homepage", work / "home.q2app")
            logs, _ = run("qr-wait", mode="waiting", storage=None)
            assert "state=qr" in logs
            logs, requests = run("login-autoplay")
            assert "state=confirm" in logs and "state=ready" in logs and "audio=playing" in logs
            assert ("/playlist/track/all", 0) in requests and ("/song/url/v1", None) in requests
            assert not any(path in ("/recommend/songs", "/user/detail", "/setting") for path, _ in requests)
            assert "remote image ready 256x256" in logs
            pixel = Image.open(artifacts / "login-autoplay.png").convert("RGB").getpixel((100, 150))
            assert max(abs(a - b) for a, b in zip(pixel, (40, 130, 210))) <= 3, pixel
            logs, requests = run("session-restored-autoplay")
            assert "audio=playing" in logs and not any(path == "/login/qr/key" for path, _ in requests)
            logs, requests = run("managed-exit-reenter", [(36, 56), (251, 194)], managed=True)
            assert "foreground Homepage (resumed)" in logs
            assert logs.count("session=restored") >= 2
            assert sum(path == "/login/status" for path, _ in requests) == 2
            assert not any(path == "/login/qr/key" for path, _ in requests)
            logs, _ = run("pause-resume", [(251, 368), *([(0, 0)] * 4), (251, 368)])
            assert "audio=paused" in logs and logs.count("audio=playing") >= 2
            logs, requests = run("next-track", [(330, 368)])
            assert sum(path == "/song/url/v1" for path, _ in requests) >= 2
            pixel = Image.open(artifacts / "next-track.png").convert("RGB").getpixel((100, 150))
            assert max(abs(a - b) for a, b in zip(pixel, (60, 130, 210))) <= 3, pixel
            logs, requests = run("previous-wrap", [(175, 368)])
            assert ("/playlist/track/all", 6) in requests
            logs, requests = run("lyrics-disabled", [(100, 150), (300, 205)])
            assert "page=lyrics" not in logs and "page=player" in logs
            assert not any(path == "/lyric" for path, _ in requests)
            run("account", [(466, 56)])
            logs, _ = run("empty-likes", mode="empty")
            assert "state=ready" in logs and "audio=playing" not in logs
            logs, _ = run("unavailable-track", mode="unavailable")
            assert "state=ready" in logs and "audio=playing" not in logs
            logs, _ = run("audio-denied", audio=False)
            assert "audio=error" in logs
            logs, _ = run("bad-audio", mode="bad-audio")
            assert "audio=error" in logs
            logs, requests = run("auto-next", mode="auto-next")
            assert sum(path == "/song/url/v1" for path, _ in requests) >= 2
            run("portrait", width=410, height=502)
            logs, requests = run("api-session-expired", mode="auth-expired")
            assert ("/login/qr/key", None) in requests
            run("permissions-denied", permission=False, storage=None)
            logs, _ = run("http-error", mode="http-error", storage=None)
            assert "state=error" in logs
            logs, _ = run("malformed", mode="malformed", storage=None)
            assert "state=error" in logs
            logs, _ = run("expired-qr", mode="expired", storage=None)
            assert "state=expired" in logs
            # Restore valid media after the intentional expired-session scenario.
            run("login-again")
            logs, _ = run("logout", [(466, 56), (200, 371)], mode="waiting")
            assert "state=qr" in logs
            logs, requests = run("session-expired", mode="invalid-session")
            assert ("/login/qr/key", None) in requests and "state=qr" in logs
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    check(args.runner.resolve(), args.artifacts.resolve())
