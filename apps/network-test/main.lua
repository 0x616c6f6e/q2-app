local q = require("q2")
local targets = require("targets")
local selected, request, now, started, last_poll = 1, nil, 0, 0, 0
local state, preview = "Ready / select a target", ""
local handles, enabled, logging = {}, false, false
local function allowed(cap)
    local available, granted = q.os.capability(cap)
    return available and granted
end
local function message(value)
    state = value
    if logging then q.os.log("info", "NETWORK " .. value) end
    if handles.state then assert(q.ui.set_text(handles.state, value)) end
end
local function render()
    assert(q.ui.clear()); assert(q.ui.background(0x111827))
    handles = {}
    local w, h = assert(q.ui.width()), assert(q.ui.height())
    if w < 240 or h < 280 then assert(q.ui.label(4, 4, "Network / screen too small")); return end
    assert(q.ui.scroll(math.max(h, 510)))
    assert(q.ui.label(16, 12, "NETWORK TEST"))
    assert(q.ui.label(16, 44, targets[selected].name))
    local url = assert(q.ui.label(16, 76, targets[selected].url))
    assert(q.ui.size(url, w - 32, 52))
    local width = math.floor((w - 48) / 3)
    handles.prev = assert(q.ui.button(16, 132, "Prev", width))
    handles.next = assert(q.ui.button(24 + width, 132, "Next", width))
    handles.start = assert(q.ui.button(32 + width * 2, 132, request and "Cancel" or "Start", width))
    handles.state = assert(q.ui.label(16, 196, state)); assert(q.ui.size(handles.state, w - 32, 54))
    -- Body preview is bounded to one Lua text value; full responses remain readable in chunks via API.
    handles.body = assert(q.ui.label(16, 258, preview)); assert(q.ui.size(handles.body, w - 32, 160))
    if allowed("apps.navigate") then handles.home = assert(q.ui.button(16, 438, "Home", 100)) end
    assert(q.ui.scroll(math.max(h, 510)))
end
local function cancel()
    if request then q.network.close(request); request = nil; message("Cancelled"); render() end
end
local function select(delta)
    cancel(); selected = (selected - 1 + delta) % #targets + 1
    preview = ""; message(enabled and "Ready / select a target" or "Network unavailable / permission denied")
    render()
end
local function start()
    if request then cancel(); return end
    if not enabled then message("Network unavailable / permission denied"); return end
    local err
    request, err = q.network.get(targets[selected].url, 5000)
    preview = ""
    if not request then message("Request rejected: " .. err.code)
    else started = now; message("Connecting...") end
    render()
end
return {
    on_start = function()
        enabled = allowed("network.http"); logging = allowed("system.log")
        if allowed("input.keys") then assert(q.keys.watch(true)) end
        if not enabled then state = "Network unavailable / permission denied" end
        render()
    end,
    on_tick = function(time)
        now = time
        if not request or now - last_poll < 100 then return end
        last_poll = now
        local result, err = q.network.status(request)
        if result == "pending" then return end
        if result then
            local code = assert(q.network.code(request))
            preview = assert(q.network.read(request, 0, 240))
            message("HTTP " .. code .. " / " .. (now - started) .. " ms")
        else message("Failed: " .. err.code .. " / " .. (now - started) .. " ms") end
        assert(q.network.close(request)); request = nil
        render()
    end,
    on_event = function(e)
        if e.type == "ui.resize" then render(); return end
        if e.type == "ui.click" then
            if e.value == handles.prev then select(-1)
            elseif e.value == handles.next then select(1)
            elseif e.value == handles.start then start()
            elseif e.value == handles.home then cancel(); q.os.exit() end
        elseif e.type == "key.action" and e.value == 1 then
            if e.text == "PREV" then select(-1)
            elseif e.text == "NEXT" then select(1)
            elseif e.text == "PLAY" then start()
            elseif e.text == "BACK" then cancel(); q.os.exit() end
        end
    end
}
