local q = require("q2")
local v, c, api = require("view"), require("cloud"), require("api")
local audio = require("playback")
local config = require("config")
local page, offset, revision, audio_revision, logging = "player", 0, -1, -1, false
local render
local exiting = false
local previous_state = "checking"
local function hint(text, y)
    v.label(24, y or v.h - 34, text, v.w - 48, v.muted, 20, "center")
end
local function auth()
    v.header("NETEASE MUSIC")
    if c.qrurl and (c.state == "qr" or c.state == "confirm") then
        local size = math.min(224, v.h - 150)
        local x = v.w >= 480 and 24 or math.floor((v.w - size) / 2)
        local id, err = q.ui.qrcode(x, 62, c.qrurl, size)
        if not id then hint("QR unavailable: " .. err.code, 122) end
        if v.w >= 480 then
            v.label(272, 86, "Scan to sign in", v.w - 296)
            v.label(272, 130, "Open Netease", v.w - 296, v.muted)
            v.label(272, 161, "Cloud Music", v.w - 296, v.muted)
            v.label(272, 205, c.state == "confirm" and "Confirm on phone" or "Use its scanner", v.w - 284, v.accent)
        end
    else
        v.image(math.floor(v.w / 2) - 40, 80, "icon", 80)
        hint(c.state == "checking" and "Connecting to your music" or "Let's try again", 193)
    end
    hint(c.message, v.h - 86)
    v.chip(24, v.h - 48, v.w - 48, c.state == "error" and "Retry" or "Refresh login QR",
        c.state == "error" and "retry" or "refresh", true)
end
local function player()
    local t = c.selected
    v.header("MY LIKED MUSIC", "account")
    if not t then
        v.image(math.floor(v.w / 2) - 40, 80, "icon", 80)
        hint(c.message, 204)
        v.chip(24, v.h - 60, v.w - 48, "Retry", "retry", true)
        return
    end
    local size = math.floor(math.min(160, v.w * 0.33, v.h - 220))
    local cover, url = v.image(24, 62, "icon", size, config.lyrics_enabled and "lyrics" or nil), t.pic_url
    if url ~= "" and q.ui.image_url then
        local sep = "?"
        for i = 1, #url do if string.byte(url, i) == 63 then sep = "&"; break end end
        q.ui.image_url(cover, url .. sep .. "param=256y256")
    end
    local x = 46 + size
    v.label(x, 70, t.title, v.w - x - 24)
    v.label(x, 109, t.artist, v.w - x - 24, v.muted)
    v.label(x, 150, t.album, v.w - x - 24, v.muted)
    if config.lyrics_enabled then v.chip(x, 188, v.w - x - 24, "Lyrics", "lyrics", true) end
    v.label(24, 230, audio.message or c.message, v.w - 48, v.accent)
    v.timeline(v.h - 124, audio.position, math.max(1, audio.duration > 0 and audio.duration or t.duration))
    local cx, y = math.floor(v.w / 2), v.h - 70
    v.label(24, y + 20, tostring(c.index or 1), 48, v.muted)
    v.image(cx - 100, y + 4, "prev", 48, "prev-track")
    v.image(cx - 28, y, audio.state == "playing" and "pause" or "play", 56, "play")
    v.image(cx + 52, y + 4, "next", 48, "next-track")
    v.image(v.w - 72, y + 4, "more", 48, "retry")
end
local function lyric_lines(raw)
    local lines, start = {}, 1
    for i = 1, math.min(#raw, 4096) do
        if string.byte(raw, i) == 10 or i == #raw then
            local line = string.sub(raw, start, string.byte(raw, i) == 10 and i - 1 or i)
            start = i + 1
            while string.sub(line, 1, 1) == "[" do
                local close
                for j = 2, math.min(#line, 64) do if string.sub(line, j, j) == "]" then close = j; break end end
                if not close then break end
                line = string.sub(line, close + 1)
            end
            if #line > 1 then lines[#lines + 1] = line end
            if #lines >= 48 then break end
        end
    end
    return lines
end
local function lyrics()
    v.header("LYRICS")
    local lines = lyric_lines(c.selected and c.selected.lyric or "")
    hint(c.selected and c.selected.title or "No track selected", 62)
    for i = 1, 5 do
        local text = lines[offset * 5 + i]
        if text then v.label(24, 108 + (i - 1) * 34, text, v.w - 48, v.ink, 20, "center") end
    end
    if #lines == 0 then hint(c.busy and "Loading lyrics..." or "No lyrics available", 168) end
    v.chip(24, v.h - 48, 110, "Prev", "lyric-prev")
    v.label(142, v.h - 36, "Read only", v.w - 284, v.muted, 20, "center")
    v.chip(v.w - 134, v.h - 48, 110, "Next", "lyric-next")
end
local function account()
    v.header("ACCOUNT")
    v.label(24, 67, c.profile.nickname or "", v.w - 48, v.accent)
    v.label(24, 110, "User ID / " .. (c.profile.uid or "--"), v.w - 48)
    v.label(24, 151, "Plays your liked music automatically", v.w - 48, v.muted)
    v.label(24, 233, c.persistent and "Session saved on this device" or "Session only / not saved", v.w - 48, v.muted)
    v.chip(24, v.h - 60, v.w - 48, "Sign out on this device", "logout", true)
end
render = function()
    v.begin()
    if v.w < 380 or v.h < 366 then
        v.label(8, 8, "Music / larger screen needed", math.max(1, v.w - 16))
        if v.w >= 80 and v.h >= 80 then v.image(16, v.h - 56, "back", 40, "exit") end
        return
    end
    if c.state ~= "ready" then auth()
    elseif page == "player" then player()
    elseif page == "lyrics" and config.lyrics_enabled then lyrics()
    else account() end
    if logging then q.os.log("info", "NCM_UI state=" .. c.state .. " page=" .. page .. " busy=" .. tostring(c.busy) .. " qr_code=" .. tostring(c.qr_code) .. " audio=" .. audio.state .. " session=" .. tostring(c.session_state()) .. " storage_error=" .. tostring(c.session_error)) end
end
local function action(name)
    if not name or exiting then return end
    if name == "exit" or (name == "back" and (page == "player" or c.state ~= "ready")) then
        c.cancel(); exiting = true; if c.exit_ready() then q.os.exit() end; return
    end
    if name == "back" then page, offset = "player", 0
    elseif name == "retry" then
        if c.selected then c.select_at(c.index) else c.retry() end
    elseif name == "refresh" then c.refresh()
    elseif name == "logout" then c.logout(); page = "player"
    elseif c.state ~= "ready" then return
    elseif name == "next-track" then c.next(1)
    elseif name == "prev-track" then c.next(-1)
    elseif name == "play" then c.play()
    elseif config.lyrics_enabled and name == "lyric-prev" then offset = math.max(0, offset - 1)
    elseif config.lyrics_enabled and name == "lyric-next" then
        local count = #lyric_lines(c.selected and c.selected.lyric or "")
        offset = math.min(math.max(0, math.ceil(count / 5) - 1), offset + 1)
    elseif (config.lyrics_enabled and name == "lyrics") or name == "account" then page, offset = name, 0 end
    render()
end

return {
    on_start = function()
        logging = api.allowed("system.log")
        if api.allowed("input.keys") then v.checked(q.keys.watch(true)) end
        c.start(); revision = c.revision; render()
    end,
    on_tick = function(now)
        if exiting then c.tick(now); if c.exit_ready() then q.os.exit() end; return end
        -- Render separately from I/O to bound callback work.
        if c.revision ~= revision or audio.revision ~= audio_revision then
            if c.state == "ready" and previous_state ~= "ready" then page, offset = "player", 0 end
            previous_state, revision, audio_revision = c.state, c.revision, audio.revision
            render(); return
        end
        c.tick(now)
    end,
    on_event = function(event)
        if event.type == "ui.resize" then render()
        elseif event.type == "ui.click" then action(v.actions[event.value])
        elseif event.type == "key.action" and event.value == 1 then
            if event.text == "BACK" then action("back")
            elseif event.text == "PLAY" then action(c.state == "ready" and "play" or "refresh")
            elseif event.text == "NEXT" then action("next-track")
            elseif event.text == "PREV" then action("prev-track") end
        end
    end
}
