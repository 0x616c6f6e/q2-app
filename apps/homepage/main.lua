-- Resident lifecycle APP. Its launcher is hidden while another independent Lua VM owns the foreground.
local q = require("q2")
local shell = require("shell")
local icon_profiles = require("icon_profiles")
local self_id, foreground, background
local selected, apps = 1, {}
local icon_button, previous, following
local notice = ""

local function checked(value, err)
    if value == nil then error(err.code) end
    return value
end

local function render()
    checked(q.ui.clear())
    icon_button, previous, following = nil, nil, nil
    local background = checked(q.appearance.get())
    if background == "home-background" then checked(q.ui.wallpaper("assets/home-background.png"))
    else checked(q.ui.background(background == "forest" and 0x20382c or 0x111827)) end
    local w, h = checked(q.ui.width()), checked(q.ui.height())
    if w < 240 or h < 240 then checked(q.ui.label(8, 8, "Q2 Home")); return end
    if #apps == 0 then
        checked(q.ui.label(0, math.floor(h / 2), "No apps", "center"))
        return
    end
    local id = apps[selected]
    -- Match the selected PNG's native size; retain responsive fallback for other screens.
    local native_size = icon_profiles[checked(q.ui.resolution())]
    local size = native_size and math.min(native_size, w - 96, math.floor(h * 0.46))
        or math.min(144, math.floor(math.min(w, h) * 0.36))
    local center_y = math.floor(h * 0.43)
    local x, y = math.floor((w - size) / 2), center_y - math.floor(size / 2)
    local icon = checked(q.apps.info(id, "icon"))
    icon_button = q.ui.image(x, y, icon, size)
    if not icon_button then
        icon_button = checked(q.ui.image(x, y, "assets/app-default.png", size))
    end
    checked(q.ui.label(0, math.floor(h * 0.72), checked(q.apps.info(id, "name")), "center"))
    if #apps > 1 then
        local margin = math.max(12, math.floor(w * 0.045))
        previous = checked(q.ui.image(margin, center_y - 24, "assets/arrow-left.png"))
        following = checked(q.ui.image(w - margin - 48, center_y - 24, "assets/arrow-right.png"))
    end
    if notice ~= "" then
        checked(q.ui.label(0, h - 38, string.sub(notice, 1, math.floor((w - 48) / 12)), "center"))
    end
end

return {
    on_start = function()
        self_id = checked(q.os.info()).app_id
        shell.start()
        -- Touch-only platforms can run the same lifecycle without a key provider.
        local available, granted = q.os.capability("input.keys")
        if available and granted then checked(q.keys.watch(true)) end
        notice = checked(q.apps.last_error())
        for i = 1, checked(q.apps.count()) do
            local id = checked(q.apps.id(i))
            if not checked(q.apps.info(id, "home")) then apps[#apps + 1] = id end
        end
        render()
    end,
    on_tick = function(now)
        local changed = shell.tick(now)
        local next_foreground = checked(q.apps.foreground())
        local next_background = checked(q.appearance.get())
        if changed or next_foreground ~= foreground or next_background ~= background then
            foreground, background = next_foreground, next_background
            if foreground == self_id then
                notice = checked(q.apps.last_error())
                render()
            end
        end
    end,
    on_event = function(event)
        if shell.event(event) then return end
        if event.type == "ui.resize" then render(); return end
        if event.type == "key.action" then
            if checked(q.apps.foreground()) ~= self_id then
                checked(q.keys.forward(event.text, event.value)); return
            end
            if event.value ~= 1 then return end
            if event.text == "PLAY" and #apps > 0 then
                local value, err = q.apps.launch(apps[selected])
                if not value then notice = err.code; render() end
            elseif (event.text == "PREV" or event.text == "NEXT") and #apps > 0 then
                selected = (selected - 1 + (event.text == "PREV" and -1 or 1)) % #apps + 1
                render()
            end
            return
        end
        if event.type ~= "ui.click" then return end
        if event.value == icon_button then
            local ok, err = q.apps.launch(apps[selected])
            if not ok then notice = "Cannot open: " .. err.code; render() end
        elseif event.value == previous or event.value == following then
            -- Wrap at either end; replace the old scene so only one APP is ever visible.
            local direction = event.value == previous and -1 or 1
            selected = (selected - 1 + direction) % #apps + 1
            notice = ""
            render()
        end
    end,
}
