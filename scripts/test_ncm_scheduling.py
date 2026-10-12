"""Deterministic callback-work regression checks inside the real sandboxed Lua runtime."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from q2app import pack

ROOT = Path(__file__).resolve().parents[1]
FAKE = r"""
local M = {data = {}, calls = 0, writes = 0, available = true, fail = false}
M.os = {capability = function() return M.available, M.available end}
local function operation()
    M.calls = M.calls + 1
    assert(M.calls <= 1, "multiple storage operations in one callback")
end
M.storage = {
    get = function(key)
        operation()
        if M.read_fail then return nil, {code = "io_error"} end
        if M.data[key] == nil then return nil, {code = "not_found"} end
        return M.data[key]
    end,
    put = function(key, value)
        operation()
        if M.fail then return nil, {code = "io_error"} end
        M.data[key] = value; return true
    end
}
M.network = {
    post = function() M.body = ""; M.opens = (M.opens or 0) + 1; return 1 end,
    write = function(_, part)
        M.writes = M.writes + 1
        assert(#part <= 255 and M.writes <= 4, "unbounded request upload")
        M.body = M.body .. part; return true
    end,
    send = function() M.sent = true; return true end,
    status = function() return "complete" end,
    code = function() return 200 end,
    close = function() M.closed = true; return true end
}
return M
"""
HARNESS = r"""
local q, f = require("q2"), require("fake")
local session, api, config = require("session"), require("api"), require("config")
local phase, ticks, cookie = 1, 0, "a"
for i = 1, 12 do cookie = cookie .. cookie end
-- Includes escaping across chunk boundaries, with an exact 4096-byte input.
cookie = string.sub(cookie, 1, 4091) .. '\"\\\n\r\t'
local escaped = string.sub(cookie, 1, 4091) .. '\\"\\\\\\n\\r\\t'
local saved_cookie = cookie
local completed = false
return {
    on_start = function()
        f.data.ncm_count, f.data.ncm_base = "14", config.base_url
        for i = 1, 14 do f.data["ncm_cookie_" .. i] = "old" end
        session.clear()
        assert(f.calls == 0, "clear must schedule, not block the event callback")
    end,
    on_tick = function(now)
        f.calls, f.writes = 0, 0
        ticks = ticks + 1
        assert(ticks < 260, "state machine stalled")
        if phase <= 6 then
            local saved, active, loaded, cleared = session.tick()
            if phase == 1 and cleared then
                assert(f.data.ncm_count == "0")
                for i = 1, 14 do assert(f.data["ncm_cookie_" .. i] == "") end
                session.save(saved_cookie); phase = 2
            elseif phase == 2 and saved then
                assert(f.data.ncm_count == "17")
                session.begin_load(); phase = 3
            elseif phase == 3 and loaded then
                assert(loaded == saved_cookie)
                session.save("replacement"); phase = 4
            elseif phase == 4 then
                assert(f.data.ncm_count == "0")
                session.begin_load(); phase = 5
            elseif phase == 5 and loaded then
                assert(loaded == "", "interrupted transaction restored")
                f.fail = true; session.clear(); phase = 6
            elseif phase == 6 and cleared ~= nil then
                assert(cleared == false, "clear failure reported success")
                f.fail, phase = false, 7
            end
        elseif phase == 7 then
            f.available = false; session.clear()
            local _, _, _, cleared = session.tick()
            assert(cleared and f.calls == 0)
            f.available = true; phase = 8
        elseif phase == 8 then
            assert(api.start("/test", {}, cookie, function(id, http, err)
                assert(id == 1 and http == 200 and err == nil and f.sent)
                local a = '{"cookie":"' .. escaped .. '","timestamp":0}'
                local b = '{"timestamp":0,"cookie":"' .. escaped .. '"}'
                assert(f.body == a or f.body == b, "chunked JSON changed cookie bytes")
                completed = true
            end))
            assert(api.active() and not f.opens, "start must enqueue without opening transport")
            phase = 9
        elseif phase == 9 then
            api.tick(now)
            if completed then
                assert(not api.active() and f.closed)
                -- Cancellation must discard partial request state without sending it later.
                f.sent = false
                api.start("/cancel", {}, cookie, function() error("cancelled callback") end)
                api.tick(now); api.close(); phase = 10
            end
        elseif phase == 10 then
            -- A read failure must remain an error, never an empty logged-out session.
            f.read_fail = true; session.begin_load(); phase = 11
        elseif phase == 11 then
            local _, _, loaded = session.tick()
            assert(loaded == nil and session.error == "io_error" and not session.pending())
            f.read_fail = false
            f.data.ncm_base, f.data.ncm_count, f.data.ncm_cookie_1 = config.base_url, "1", "legacy"
            session.begin_load(); phase = 12
        elseif phase == 12 then
            local _, _, loaded = session.tick()
            if loaded then assert(loaded == "legacy"); phase = 13 end
        else
            assert(not api.tick(now) and not f.sent and not api.active())
            q.os.log("info", "NCM_SCHEDULING_PASS")
            q.os.exit()
        end
    end
}
"""


CLOUD_API = r"""
local M = {now = 0}
function M.close() M.callback = nil end
function M.active() return M.callback ~= nil end
function M.start(_, _, _, callback) M.started = true; M.callback = callback; return true end
function M.tick(now)
    M.now = now
    if not M.callback then return false end
    local callback = M.callback; M.callback = nil; M.completed = true
    callback(1, 200); return true
end
function M.value(_, path)
    if path == "/code" then return 200 end
    if path == "/data/profile/userId" then return 42 end
end
return M
"""
CLOUD_HARNESS = r"""
local q, cloud, api = require("q2"), require("cloud"), require("cloud_api")
local ticks = 0
return {
    on_start = function() cloud.start() end,
    on_tick = function(now)
        ticks = ticks + 1; assert(ticks < 30)
        api.started, api.completed = false, false
        cloud.tick(now)
        assert(not (api.started and api.completed), "response and follow-up share a callback")
        if cloud.state == "ready" then q.os.log("info", "NCM_CLOUD_PASS"); q.os.exit() end
    end
}
"""


def check(runner):
    with tempfile.TemporaryDirectory(prefix="q2-ncm-budget-") as directory:
        work = Path(directory)
        (work / "src").mkdir()
        manifest = json.loads((ROOT / "apps/music-player/manifest.json").read_text())
        manifest.pop("icon", None)
        manifest["capabilities"] = {"required": ["system.log"], "optional": []}
        (work / "manifest.json").write_text(json.dumps(manifest))
        (work / "main.lua").write_text(HARNESS)
        for name in ("api", "session", "config"):
            text = (ROOT / "apps/music-player/src" / (name + ".lua")).read_text()
            (work / "src" / (name + ".lua")).write_text(text.replace('require("q2")', 'require("fake")'))
        (work / "src/fake.lua").write_text(FAKE)
        pack(work, work / "out/test.q2app")
        args = [
            str(runner),
            str(work / "out/test.run/manifest.json"),
            str(work / "out/test.run/main.lua"),
            "--headless",
            "--frames",
            "280",
            "--grant",
            "system.log",
        ]
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        logs = result.stdout + result.stderr
        assert result.returncode == 0 and "NCM_SCHEDULING_PASS" in logs, logs
        print("PASS: bounded session I/O, interrupted save, clear failure, 4096-byte POST and cancel")
        (work / "main.lua").write_text(CLOUD_HARNESS)
        cloud = (ROOT / "apps/music-player/src/cloud.lua").read_text()
        cloud = cloud.replace('require("api")', 'require("cloud_api")')
        cloud = cloud.replace('require("session")', 'require("cloud_session")')
        (work / "src/cloud.lua").write_text(cloud)
        (work / "src/playback.lua").write_text(
            'return {state="idle",stop=function() end,tick=function() end}'
        )
        (work / "src/cloud_api.lua").write_text(CLOUD_API)
        (work / "src/cloud_session.lua").write_text(
            "local loading; return {begin_load=function() loading=true end, tick=function() "
            'if loading then loading=false; return nil,true,"synthetic" end return nil,false end}'
        )
        pack(work, work / "out/test.q2app")
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        logs = result.stdout + result.stderr
        assert result.returncode == 0 and "NCM_CLOUD_PASS" in logs, logs
        print("PASS: login response and follow-up use separate callbacks")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", required=True, type=Path)
    check(parser.parse_args().runner.resolve())
