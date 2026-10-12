local q = require("q2")
local status, play, next_track, home
local playing, track = false, 1
-- Presentation-only demo; layout derives from the actual viewport, including 502x410.
local function render()
    assert(q.ui.clear())
    status, play, next_track, home = nil, nil, nil, nil
    local info = assert(q.os.info())
    local width, height = assert(q.ui.width()), assert(q.ui.height())
    assert(q.ui.background(0x111827))
    if width < 240 or height < 280 then
        assert(q.ui.label(4, 4, "Display too small"))
        return
    end
    local function y(reference) return math.floor(reference * height / 502) end
    local button_width = math.min(160, math.floor((width - 72) / 2))
    assert(q.ui.label(24, 22, "Q2  /  MINI SYSTEM"))
    -- Select a device profile by full display size; place widgets within the current viewport.
    local resolution = assert(q.ui.resolution())
    assert(q.ui.label(24, y(66), "Display " .. resolution))
    assert(q.ui.label(24, y(112), "LVGL 9.3  |  Lua API " .. info.api))
    if height >= 360 then assert(q.ui.label(24, y(160), "One kernel. Independent apps.")) end
    status = assert(q.ui.label(24, y(216), "Track " .. track .. (playing and " / playing" or " / paused")))
    play = assert(q.ui.button(24, y(272), playing and "Pause" or "Play", button_width))
    next_track = assert(q.ui.button(48 + button_width, y(272), "Next", button_width))
    local available, granted = q.os.capability("apps.navigate")
    if available and granted and height >= 360 then
        home = assert(q.ui.button(24, height - 110, "Home", button_width))
    elseif height >= 360 then
        assert(q.ui.label(24, y(356), "Click a button to send a Lua event."))
    end
    assert(q.ui.label(24, height - 44, "UI demo / no audio output"))
end
return {
    on_start = render,
    on_event = function(event)
        if event.type == "ui.resize" then render(); return end
        if event.type ~= "ui.click" or not status then return end
        if event.value == home then q.os.exit(); return end
        if event.value == play then
            playing = not playing
            assert(q.ui.set_text(play, playing and "Pause" or "Play"))
        elseif event.value == next_track then
            track = track + 1
        end
        assert(q.ui.set_text(status, "Track " .. track .. (playing and " / playing" or " / paused")))
    end,
}
