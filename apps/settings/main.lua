-- Factory settings: one scrollable vertical list, with persisted system preferences.
local q = require("q2")
local view = require("view")
local buttons, page, notice, background = {}, "settings", "", "home-background"
local graphical, shared, persistent, navigation, system, keys
local function ok(value, err)
    if value == nil then error(err.code) end
    return value
end
local function can(cap)
    local available, granted = q.os.capability(cap)
    return available and granted
end
local function get(name) return ok(q.shell.get(name)) end
local function caption(value) return value and "On" or "Off" end
local function save_background(choice)
    local success, err
    if shared and can("appearance.write") then success, err = q.appearance.set(choice)
    elseif persistent then success, err = q.storage.put("background", choice)
    else success = true end
    if not success then notice = "Save failed: " .. err.code; return end
    background = choice
    notice = persistent and "Saved" or "Session only"
end
local function render(preserve)
    if not graphical then return end
    local offset = preserve and q.ui.scroll_y() or 0
    ok(q.ui.clear()); buttons = {}
    view.begin(background)
    local w, h = q.ui.width(), q.ui.height()
    if w < 240 or h < 100 then view.label(4, 4, "Settings"); return end
    ok(q.ui.scroll(system and 1030 or 370))
    view.label(16, 20, "Settings")
    if navigation then buttons.exit = view.button(w - 112, 12, "Home", 96) end
    local y = 84
    local function row(id, title)
        buttons[id] = view.button(16, y, title, w - 32)
        y = y + 64
    end
    if page == "background" then
        row("home-background", "Home background")
        row("midnight", "Midnight")
        row("forest", "Forest")
        row("back", "Back")
    else
        row("background", "Background: " .. background)
        if system then
            row("status_bar", "Status bar: " .. caption(get("status_bar")))
            row("status_left", "Bar left: " .. get("status_left"))
            row("status_right", "Bar right: " .. get("status_right"))
            row("screensaver", "Screensaver: " .. caption(get("screensaver")))
            row("idle_timeout_ms", "Idle: " .. get("idle_timeout_ms") / 1000 .. " seconds")
            row("clock_move_interval_ms", "Clock move: " .. get("clock_move_interval_ms") / 1000 .. " seconds")
            row("saver_text", "Saver: " .. get("saver_text"))
            row("lock_enabled", "Lock on saver: " .. caption(get("lock_enabled")))
            row("unlock_key", "Unlock key: " .. get("unlock_key"))
            local actions = {"Single", "Double", "Long"}
            row("unlock_action", "Unlock: " .. actions[get("unlock_action")])
            view.label(16, y, get("persistent") and "System preferences saved" or "System preferences: session only")
            y = y + 32
        else
            view.label(16, y, "System settings need factory access"); y = y + 32
        end
        view.label(16, y, "Viewport: " .. w .. " x " .. h); y = y + 32
    end
    view.label(16, y, notice ~= "" and notice or "Scroll or drag for more")
    if preserve then ok(q.ui.scroll_y(offset)) end
end
local choices = {
    status_left = {"{time}", "Q2", "{battery}"},
    status_right = {"{wifi} {bt} {ble} {battery}", "{battery}", "{time}"},
    saver_text = {"{time}", "Q2  {time}", "{battery}"},
    idle_timeout_ms = {15000, 30000, 60000, 120000},
    clock_move_interval_ms = {5000, 10000, 30000},
    unlock_action = {1, 2, 3},
}
local function change(name)
    local current = get(name)
    local value
    if type(current) == "boolean" then value = not current
    else
        local values = choices[name]
        if name == "unlock_key" then
            values = {}
            if keys then
                for i = 1, ok(q.keys.count()) do values[#values + 1] = ok(q.keys.name(i)) end
            end
        end
        if not values or #values == 0 then notice = "No registered keys"; return end
        value = values[1]
        for i, item in ipairs(values) do if item == current then value = values[i % #values + 1]; break end end
    end
    local success, err = q.shell.set(name, value)
    notice = success and (get("persistent") and "Saved" or "Session only") or ("Save failed: " .. err.code)
end
return {
    on_start = function()
        graphical, shared, persistent = can("display.ui"), can("appearance.read"), can("storage.private")
        navigation = can("apps.navigate")
        system = can("system.ui.read") and can("system.settings") and navigation
        keys = can("input.keys")
        if keys then ok(q.keys.watch(true)) end
        if shared then background = ok(q.appearance.get()); persistent = ok(q.appearance.persistent())
        elseif persistent then
            local saved = q.storage.get("background")
            if saved == "home-background" or saved == "midnight" or saved == "forest" then background = saved end
        end
        if graphical then render(false)
        else view.line(0, "Q2 / System settings"); view.line(28, "Display unavailable") end
    end,
    on_event = function(event)
        if event.type == "ui.resize" then render(true); return end
        if event.type == "key.action" and event.value == 1 then
            if event.text == "BACK" and navigation then ok(q.os.exit())
            elseif graphical and (event.text == "PREV" or event.text == "NEXT") then
                local y = q.ui.scroll_y() + (event.text == "NEXT" and 100 or -100)
                ok(q.ui.scroll_y(math.max(0, y)))
            end
            return
        end
        if not graphical or event.type ~= "ui.click" then return end
        for name, handle in pairs(buttons) do if handle == event.value then
            if name == "exit" then ok(q.os.exit()); return
            elseif name == "background" then page = "background"; render(false)
            elseif name == "back" then page = "settings"; render(false)
            elseif name == "home-background" or name == "midnight" or name == "forest" then
                save_background(name); render(true)
            else change(name); render(true) end
            return
        end end
    end,
}
