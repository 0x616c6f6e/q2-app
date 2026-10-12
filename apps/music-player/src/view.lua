-- Small reusable drawing helpers; only existing public Lua display APIs are used.
local q = require("q2")
local M = {ink = 0xf1e8d5, muted = 0x98aaa0, accent = 0xf0aa70, actions = {}}
function M.checked(value, err)
    if value == nil then error(err.code) end
    return value
end
local ok = M.checked
function M.begin()
    ok(q.ui.clear()); ok(q.ui.scroll(0)); ok(q.ui.background(0x101c19))
    M.actions = {}
    M.w, M.h = q.ui.width(), q.ui.height()
end
function M.label(x, y, text, width, color, font, align)
    -- Preserve UTF-8 boundaries within the 255-byte display argument limit.
    local limit, i = math.min(#text, 220), 1
    while i <= limit do
        local byte = string.byte(text, i)
        local step = byte < 128 and 1 or byte < 224 and 2 or byte < 240 and 3 or 4
        if i + step - 1 > limit then break end
        i = i + step
    end
    text = string.sub(text, 1, i - 1)
    local id = ok(q.ui.label(x, y, text, align or "left"))
    ok(q.ui.style(id, font or 20, color or M.ink))
    ok(q.ui.size(id, width, font == 40 and 48 or 26))
    return id
end
function M.image(x, y, name, size, action)
    local id
    if size then id = ok(q.ui.image(x, y, "assets/" .. name .. ".png", size))
    else id = ok(q.ui.image(x, y, "assets/" .. name .. ".png")) end
    if action then M.actions[id] = action end
    return id
end
function M.panel(x, y, width, height, action)
    local id = M.image(x, y, "row")
    ok(q.ui.size(id, width, height))
    if action then M.actions[id] = action end
    return id
end
function M.header(title, more)
    M.image(16, 4, "back", 40, "back")
    M.label(64, 13, title, M.w - 128, M.ink, 20, "center")
    if more then M.image(M.w - 56, 4, "more", 40, more) end
end
function M.time(seconds)
    local minutes = math.floor(seconds / 60)
    seconds = math.floor(seconds % 60)
    return minutes .. ":" .. (seconds < 10 and "0" or "") .. seconds
end
function M.timeline(y, elapsed, duration)
    local width = M.w - 48
    local rail = M.image(24, y, "rail", nil, "seek")
    ok(q.ui.size(rail, width, 8))
    local fill = M.image(24, y, "fill", nil, "seek")
    ok(q.ui.size(fill, math.max(1, math.floor(width * elapsed / duration)), 8))
    local stamp = M.label(24, y + 14, M.time(elapsed), 90, M.muted)
    M.label(M.w - 114, y + 14, M.time(duration), 90, M.muted, 20, "right")
    return fill, stamp, width
end
function M.chip(x, y, width, text, action, active)
    M.panel(x, y, width, 42, action)
    M.label(x + 4, y + 8, text, width - 8, active and M.accent or M.muted, 20, "center")
end
return M
