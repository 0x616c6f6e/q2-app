local api = require("api")
local store = require("session")
local audio = require("playback")
local config = require("config")
local M = {state = "checking", message = "Checking login...", cookie = "", profile = {},
    tracks = {}, busy = false, persistent = false, revision = 0}
local queued, poll_at, qr_started, last_job = nil, 0, 0, nil
local function change(message)
    if message then M.message = message end
    M.revision = M.revision + 1
end
local function fail(message)
    M.busy = false
    if M.state ~= "ready" then M.state = "error" end
    change(message)
end
local function schedule(kind, path, fields)
    queued = {kind = kind, path = path, fields = fields or {}}
    last_job = queued
    M.busy = true
end
local function qr()
    M.state, M.qrurl, M.key = "checking", nil, nil
    change("Creating login QR...")
    schedule("key", "/login/qr/key")
end
local function signed_out(message)
    M.state = "checking"
    audio.stop()
    M.cookie, M.profile, M.tracks, M.selected = "", {}, {}, nil
    M.persistent = false
    queued = nil; M.busy = true
    store.clear()
    change(message or "Clearing saved session...")
end
local function value(id, path, fallback)
    local v = api.value(id, path)
    if v == nil or (fallback ~= nil and type(v) ~= type(fallback)) then return fallback end
    return v
end
local function track(id, prefix)
    return {id = value(id, prefix .. "/id", 0), title = value(id, prefix .. "/name", "Untitled"),
        artist = value(id, prefix .. "/ar/0/name", "Unknown artist"),
        album = value(id, prefix .. "/al/name", ""), pic_url = value(id, prefix .. "/al/picUrl", ""),
        duration = math.floor(value(id, prefix .. "/dt", 0) / 1000)}
end
local function complete(job, id, http, err)
    M.busy = false
    if not id then fail("Network: " .. (err or "unknown") .. " / retry"); return end
    if http == 301 or http == 401 then signed_out("Session expired / scan again"); return end
    if http < 200 or http >= 300 then fail("HTTP " .. http .. " / retry"); return end
    local code = value(id, "/code", value(id, "/data/code", 0))
    if code == 301 or code == 401 then signed_out("Session expired / scan again"); return end
    if job.kind == "status" then
        if code ~= 200 then fail("Login status rejected: " .. code); return end
        local uid = value(id, "/data/profile/userId", 0)
        if uid <= 0 or M.cookie == "" then signed_out(); return end
        M.profile = {uid = uid, nickname = value(id, "/data/profile/nickname", "Music lover"),
            vip = value(id, "/data/profile/vipType", 0)}
        M.state = "ready"
        M.tracks, M.selected, M.favorites = {}, nil, nil
        change("Loading liked music...")
        schedule("favorites", "/user/playlist", {uid = uid, limit = 10, offset = 0})
    elseif job.kind == "key" then
        M.key = value(id, "/data/unikey", "")
        if code ~= 200 or M.key == "" then fail("Could not create login key"); return end
        schedule("qr", "/login/qr/create", {key = M.key, platform = "pc"})
    elseif job.kind == "qr" then
        M.qrurl = value(id, "/data/qrurl", "")
        if code ~= 200 or string.sub(M.qrurl, 1, 36) ~= "https://music.163.com/login?codekey=" then
            fail("Unexpected QR response"); return
        end
        M.state = "qr"; qr_started = api.now; poll_at = api.now + config.poll_ms
        change("Scan with Netease Cloud Music")
    elseif job.kind == "check" then
        M.qr_code = code
        if code == 800 then M.state = "expired"; change("QR expired / refresh to continue")
        elseif code == 801 or code == 802 then
            M.state = code == 802 and "confirm" or "qr"
            poll_at = api.now + config.poll_ms
            change(code == 802 and "Confirm sign-in on your phone" or "Scan with Netease Cloud Music")
        elseif code == 803 then
            local cookie = api.long(id, "/cookie", 4096)
            if not cookie or cookie == "" then fail("Login returned no usable session"); return end
            M.cookie = cookie
            M.persistent = store.save(cookie)
            M.state, M.qrurl, M.key = "checking", nil, nil
            change("Signed in / checking account...")
            schedule("status", "/login/status")
        else fail("Login check rejected: " .. code) end
    elseif code ~= 200 then fail("API rejected request: " .. code)
    elseif job.kind == "favorites" then
        local count = value(id, "/playlist", -1)
        if count < 0 then fail("Invalid library response"); return end
        for i = 0, math.min(count, 10) - 1 do
            local p = "/playlist/" .. i
            if value(id, p .. "/specialType", 0) == 5 and
                value(id, p .. "/creator/userId", 0) == M.profile.uid then
                M.favorites = {id = value(id, p .. "/id", 0), count = value(id, p .. "/trackCount", 0)}
                break
            end
        end
        if M.favorites then
            if M.favorites.count == 0 then change("Like some songs in Netease first"); return end
            M.select_at(1)
        elseif value(id, "/more", false) and count > 0 and job.fields.offset < 1000 then
            schedule("favorites", "/user/playlist", {uid = M.profile.uid, limit = 10,
                offset = job.fields.offset + count})
        else change("No liked-music library found") end
    elseif job.kind == "tracks" then
        local count = value(id, "/songs", -1)
        if count < 0 then fail("Invalid track response"); return end
        M.tracks, M.offset = {}, job.fields.offset
        for i = 0, math.min(count, config.page_size) - 1 do
            M.tracks[#M.tracks + 1] = track(id, "/songs/" .. i)
        end
        if #M.tracks == 0 then change("No playable tracks in this library"); return end
        M.select_at(math.min(M.wanted, M.offset + #M.tracks))
    elseif job.kind == "url" then
        local url = api.long(id, "/data/0/url", 2048)
        M.selected.trial = value(id, "/data/0/freeTrialInfo/start", nil) ~= nil
        if not url or url == "" then change("Track unavailable for this account")
        else
            audio.start(url)
            change(M.selected.trial and "Preview" or "My liked music")
        end
        if config.lyrics_enabled then schedule("lyric", "/lyric", {id = M.selected.id}) end
    elseif job.kind == "lyric" then
        M.selected.lyric = api.long(id, "/lrc/lyric", 8192) or ""
        change()
    end
end
function M.start()
    audio.stop(); api.close(); queued = nil
    M.cookie, M.persistent, M.session_error, M.exiting = "", false, nil, false
    M.state = "checking"; change("Checking login...")
    store.begin_load()
end
function M.tick(now)
    api.now = now
    audio.tick(now)
    if audio.state == "ended" and not M.busy and M.selected then M.next(1); return end
    local saved, writing, cookie, cleared = store.tick()
    if store.error and store.error ~= M.session_error then
        M.session_error = store.error
        fail("Session storage: " .. store.error .. " / retry")
        queued = nil
    end
    if M.exiting then return end
    if store.error then return end
    if cleared == false then fail("Cannot clear saved session / retry")
    elseif cleared then qr() end
    if cookie ~= nil then
        M.cookie, M.persistent = cookie, cookie ~= ""
        schedule("status", "/login/status")
    end
    if saved ~= nil then M.persistent = saved; change() end
    if writing then return end
    -- Defer follow-up I/O to the next tick.
    if api.tick(now) then return end
    if queued then
        local job = queued; queued = nil
        local sent, err = api.start(job.path, job.fields, M.cookie,
            function(id, http, error) complete(job, id, http, error) end)
        if not sent then fail(err) end
    elseif not api.active() and (M.state == "qr" or M.state == "confirm") then
        if now - qr_started > 180000 then M.state = "expired"; change("QR expired / refresh to continue")
        elseif now >= poll_at then schedule("check", "/login/qr/check", {key = M.key, noCookie = true}) end
    end
end
function M.refresh()
    api.close(); queued = nil; qr()
end
function M.retry()
    if M.state ~= "ready" then M.start()
    elseif last_job then schedule(last_job.kind, last_job.path, last_job.fields); change("Retrying...") end
end
function M.logout()
    api.close(); queued = nil; signed_out()
end
function M.select_at(index)
    if not M.favorites or M.favorites.count <= 0 then return end
    api.close(); queued = nil; audio.stop()
    index = ((index - 1) % M.favorites.count) + 1
    M.wanted = index
    local offset = math.floor((index - 1) / config.page_size) * config.page_size
    if offset ~= M.offset or not M.tracks[index - offset] then
        schedule("tracks", "/playlist/track/all", {id = M.favorites.id, limit = config.page_size, offset = offset})
        change("Loading liked music..."); return
    end
    M.selected, M.index = M.tracks[index - offset], index
    M.selected.lyric = nil
    schedule("url", "/song/url/v1", {id = M.selected.id, level = "standard"})
    change("Loading track...")
end
function M.next(direction)
    M.select_at((M.index or 1) + direction)
end
function M.play()
    if audio.state == "error" or audio.state == "idle" then
        if M.index then M.select_at(M.index) else M.retry() end
    else audio.toggle() end
end
function M.session_state() return store.state end
function M.exit_ready() return not store.pending() end
function M.cancel()
    M.exiting = true
    audio.stop(); api.close(); queued = nil; M.busy = false
end
return M
