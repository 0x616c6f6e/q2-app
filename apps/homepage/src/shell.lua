-- Resident UI policy. Kernel supplies isolated layers/status/input primitives only.
local q = require("q2")
local M = {}
local icons = require("status_icons")
local status_signature = ""
local mode, revision, last_tick, idle_since, last_move, step = "awake", -1, 0, 0, 0, 0
local clock, hint, clock_width, clock_height
local previous_clock = ""
local cfg = {}
local data_enabled = false
local samples = {}
local topics = {
    time = "system.clock.time", battery = "power.battery.percent",
    charging = "power.battery.charging", wifi = "wireless.wifi.connected",
    bt = "wireless.bt.connected", ble = "wireless.ble.connected",
    wifi_rssi = "wireless.wifi.rssi_dbm", wifi_enabled = "wireless.wifi.enabled", ble_state = "wireless.ble.state"
}
local function status_text(name)
    if not data_enabled then return name == "ble" and "" or q.shell.get(name) end
    if name == "time" then return samples.time or "--:--" end
    if name == "battery" then
        if samples.battery == nil then return "BAT --" end
        return (samples.charging and "+" or "") .. samples.battery .. "%"
    end
    return samples[name] == true and (name == "wifi" and "WiFi" or name == "ble" and "BLE" or "BT") or ""
end
local function ok(value, err)
    if value == nil then error(err.code) end
    return value
end
local function get(name) return ok(q.shell.get(name)) end
local function text(template, images)
    -- Bounded token expansion: no string.format/gsub or host Lua libraries are needed.
    local result, i = "", 1
    while i <= #template and #result < 220 do
        local token = nil
        for _, name in ipairs({"time", "battery", "wifi", "bt", "ble"}) do
            local marker = "{" .. name .. "}"
            if string.sub(template, i, i + #marker - 1) == marker then token = name; i = i + #marker; break end
        end
        if token then
            if images and data_enabled and (token == "wifi" or token == "ble" or token == "battery") then
                -- Bounded by the 127-byte template and the scene's 48 widget quota.
                images[#images + 1] = token
            else result = result .. status_text(token) end
        else result = result .. string.sub(template, i, i); i = i + 1 end
    end
    return string.sub(result, 1, 240)
end
local function present(next_mode)
    mode = next_mode
    ok(q.shell.present(mode))
    if mode == "awake" then idle_since = get("last_activity") end
end
local function draw_status(force)
    local wifi = icons.wifi(samples.wifi, samples.wifi_rssi, samples.wifi_enabled)
    local ble = icons.ble(samples.ble, samples.ble_state)
    local battery = icons.battery(samples.battery, samples.charging)
    local signature = cfg.status_left .. cfg.status_right .. text(cfg.status_left) .. text(cfg.status_right)
        .. (wifi or "?") .. (ble or "?") .. (battery or "?")
    if not force and signature == status_signature then return end
    status_signature = signature
    ok(q.shell.layer("status")); ok(q.ui.clear()); ok(q.ui.background(0x0b1018))
    local w, h = q.ui.width(), q.ui.height()
    local size, gap = math.min(24, h - 4), 5
    local choices = {wifi = wifi, ble = ble, battery = battery}
    for side = 1, 2 do
        local tokens = {}
        local label = text(side == 1 and cfg.status_left or cfg.status_right, tokens)
        local x = side == 1 and 8 or math.floor(w / 2)
        local width = math.max(1, math.floor(w / 2) - (side == 1 and 12 or 8))
        -- Keep each configured half independent; omit percentage if only icons fit.
        local count = math.min(#tokens, math.floor(width / (size + gap)))
        local numeric = false
        for i = 1, count do if tokens[i] == "battery" and samples.battery ~= nil then numeric = true end end
        numeric = numeric and width >= count * (size + gap) + 56
        local occupied = count * (size + gap) + (numeric and 56 or 0)
        if label ~= "" and width > occupied then
            local handle = ok(q.ui.label(x, math.max(0, math.floor((h - 24) / 2)), label, side == 1 and "left" or "right"))
            ok(q.ui.size(handle, width - occupied, h))
        end
        local cursor = x + width - occupied
        for i = 1, count do
            local name = tokens[i]
            local asset = choices[name]
            if asset then ok(q.ui.image(cursor, math.floor((h - size) / 2), "assets/status-" .. asset .. ".png", size))
            else
                -- Missing/error/expired samples must not masquerade as a disconnected radio or empty battery.
                local handle = ok(q.ui.label(cursor, math.max(0, math.floor((h - 24) / 2)), "--", "center"))
                ok(q.ui.size(handle, size, h))
            end
            cursor = cursor + size + gap
            if numeric and name == "battery" then
                local handle = ok(q.ui.label(cursor, math.max(0, math.floor((h - 24) / 2)), samples.battery .. "%"))
                ok(q.ui.size(handle, 56, h)); cursor = cursor + 56
                numeric = false
            end
        end
    end
end
local function draw()
    draw_status(true)
    local w, h
    ok(q.shell.layer("saver")); ok(q.ui.clear()); ok(q.ui.background(0x000000))
    w, h = q.ui.width(), q.ui.height()
    clock_width = math.min(w - 16, cfg.saver_text == "{time}" and 160 or 300)
    clock_height = w >= 200 and h >= 90 and 50 or 28
    clock = ok(q.ui.label(0, 0, "", "center"))
    ok(q.ui.style(clock, clock_height == 50 and 40 or 20, 0x88939f))
    ok(q.ui.size(clock, clock_width, clock_height))
    ok(q.ui.position(clock, math.floor((w - clock_width) / 2), math.max(0, math.floor((h - clock_height) / 2))))
    if h >= 120 then
        hint = ok(q.ui.label(8, h - 36, "", "center")); ok(q.ui.size(hint, w - 16, 28))
    else hint = nil end
    previous_clock = ""
    ok(q.shell.layer("home"))
end
local function refresh_config()
    for _, name in ipairs({"status_bar", "screensaver", "lock_enabled", "idle_timeout_ms",
        "clock_move_interval_ms", "status_left", "status_right", "saver_text", "unlock_key", "unlock_action"}) do
        cfg[name] = get(name)
    end
    revision = get("revision")
    draw()
end
function M.start()
    local available, granted = q.os.capability("data.read")
    data_enabled = available and granted
    if data_enabled then
        for name, topic in pairs(topics) do
            -- Unknown/unavailable/denied status remains unknown; do not fabricate zero battery.
            samples[name] = q.data.get(topic)
            local subscription, err = q.data.subscribe(topic)
            if not subscription and err.code ~= "permission_denied" and err.code ~= "not_found" then
                error(err.code)
            end
        end
    end
    refresh_config()
    idle_since = get("last_activity")
    present("awake")
end
function M.tick(now)
    if now - last_tick < 50 then return false end
    last_tick = now
    local changed = revision ~= get("revision")
    if changed then refresh_config() end
    local activity = get("last_activity")
    idle_since = math.max(idle_since, activity)
    if not cfg.screensaver and mode ~= "awake" then present("awake") end
    if cfg.screensaver and mode == "awake" and now - idle_since >= cfg.idle_timeout_ms then
        present(cfg.lock_enabled and "locked" or "saver")
        last_move, step = now, 0
    end
    -- Legacy snapshots remain textual when the data component is disabled.
    draw_status(false)
    ok(q.shell.layer("saver"))
    local value = text(cfg.saver_text)
    if value ~= previous_clock then ok(q.ui.set_text(clock, value)); previous_clock = value end
    if hint then
        local actions = {"Single", "Double", "Long"}
        ok(q.ui.set_text(hint, mode == "locked" and (actions[cfg.unlock_action] .. " " .. cfg.unlock_key .. " to unlock") or ""))
    end
    if mode ~= "awake" and now - last_move >= cfg.clock_move_interval_ms then
        last_move, step = now, step + 1
        local dx = math.max(0, q.ui.width() - clock_width - 16)
        local margin = math.min(8, math.max(0, math.floor((q.ui.height() - clock_height) / 2)))
        local dy = math.max(0, q.ui.height() - clock_height - 2 * margin - (hint and 40 or 0))
        ok(q.ui.position(clock, 8 + step * 37 % (dx + 1), margin + step * 23 % (dy + 1)))
    end
    ok(q.shell.layer("home"))
    return changed
end
function M.event(event)
    if event.type == "data.changed" then
        for name, topic in pairs(topics) do
            if topic == event.key then
                if event.valid then samples[name] = event.value else samples[name] = nil end
                return true
            end
        end
    end
    if event.type == "shell.wake" then
        if mode == "saver" then present("awake") end
        return true
    end
    if event.type == "key.action" and mode ~= "awake" then
        if mode == "saver" or (event.text == cfg.unlock_key and event.value == cfg.unlock_action) then
            present("awake")
        end
        return true -- Unlock is never forwarded to the foreground APP.
    end
    return false
end
return M
