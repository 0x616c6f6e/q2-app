local q = require("q2")
-- Change this fixed string and rebuild the APP to generate different content (1..255 UTF-8 bytes).
local content = "Q2-Kernel"
local exit_button
local function render()
    assert(q.ui.clear()); assert(q.ui.background(0x111827))
    local w, h = assert(q.ui.width()), assert(q.ui.height())
    exit_button = nil
    if w < 200 or h < 240 then
        assert(q.ui.label(4, 4, "QR Code / screen too small")); return
    end
    assert(q.ui.label(0, 10, "QR Code", "center"))
    local size = math.min(280, w - 32, h - 150)
    -- The provider adds a white quiet zone and draws whole pixels for each QR module.
    local code, err = q.ui.qrcode(math.floor((w - size) / 2), 42, content, size)
    if not code then
        local label = assert(q.ui.label(16, 70, "QR unavailable: " .. err.code))
        assert(q.ui.size(label, w - 32, 80))
    else
        local label = assert(q.ui.label(16, 50 + size, content, "center"))
        assert(q.ui.size(label, w - 32, 40))
    end
    exit_button = assert(q.ui.button(math.floor((w - 100) / 2), h - 56, "Back", 100))
end
return {
    on_start = function()
        local available, granted = q.os.capability("input.keys")
        if available and granted then assert(q.keys.watch(true)) end
        render()
    end,
    on_event = function(event)
        if event.type == "ui.resize" then render()
        elseif event.type == "ui.click" and event.value == exit_button then q.os.exit()
        elseif event.type == "key.action" and event.text == "BACK" and event.value == 1 then q.os.exit() end
    end
}
