-- Portable application; it can run without a display provider.
local q = require('q2')
local home
local function render()
    home = nil
    local info, err = q.os.info()
    if not info then error(err.code) end
    local ui, ui_granted = q.os.capability('display.ui')
    local nav, nav_granted = q.os.capability('apps.navigate')
    if ui and ui_granted then assert(q.ui.clear()) end
    if ui and ui_granted and q.ui.width() >= 240 and q.ui.height() >= 240 then
        assert(q.ui.label(24, 24, 'Device information'))
        assert(q.ui.label(24, 76, info.name .. ' / API ' .. info.api))
        if nav and nav_granted then home = assert(q.ui.button(24, 140, 'Home')) end
        return
    end
    local available, granted = q.os.capability('display.text')
    if available and granted then
        local ok, display_error = q.display.text(0, 0, info.name .. ' API ' .. info.api)
        if not ok then error(display_error.code) end
    end
end
return {
    on_start = render,
    on_event = function(event)
        if event.type == 'ui.resize' then render(); return end
        if home and event.type == 'ui.click' and event.value == home then q.os.exit() end
    end
}
