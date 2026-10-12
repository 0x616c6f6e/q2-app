local q = require("q2")
local api = require("api")
local M = {state = "idle", position = 0, duration = 0, revision = 0}
local pending, poll_at
local function change(state, message)
    if M.state ~= state or M.message ~= message then M.revision = M.revision + 1 end
    M.state, M.message = state, message
end
function M.stop()
    pending = nil
    if api.allowed("audio.playback") then q.audio.stop() end
    M.position, M.duration = 0, 0
    change("idle")
end
function M.start(url)
    M.stop()
    if not api.allowed("audio.playback") then change("error", "Audio unavailable / permission denied"); return end
    local ok, err = q.audio.open()
    if not ok then change("error", "Audio: " .. err.code); return end
    pending = {url = url, offset = 1, deadline = api.now + 10000}
    change("buffering", "Buffering...")
end
function M.toggle()
    if M.state == "playing" or M.state == "paused" then
        local ok, err = q.audio.pause(M.state == "playing")
        if not ok then change("error", "Audio: " .. err.code) end
    end
end
function M.tick(now)
    if pending then
        local ok, err
        if pending.offset <= #pending.url then
            ok, err = q.audio.write(string.sub(pending.url, pending.offset, pending.offset + 254))
            if ok then pending.offset = pending.offset + 255 end
        else
            ok, err = q.audio.play()
            if not ok and err.code == "busy" and now < pending.deadline then return end
            if ok then pending = nil; poll_at = 0 end
        end
        if not ok then pending = nil; q.audio.stop(); change("error", "Audio: " .. err.code) end
        return
    end
    if M.state == "idle" or M.state == "error" or now < (poll_at or 0) then return end
    poll_at = now + 200
    local state, err = q.audio.state()
    if not state then change("error", "Audio: " .. err.code); return end
    local position = math.floor((q.audio.position() or 0) / 1000)
    M.duration = math.floor((q.audio.duration() or 0) / 1000)
    if position ~= M.position then M.position = position; M.revision = M.revision + 1 end
    change(state, state == "buffering" and "Buffering..." or nil)
end
return M
