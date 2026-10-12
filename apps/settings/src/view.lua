local q = require("q2")
local view = {}
local function checked(value, err)
    if value == nil then error(err.code) end
    return value
end
function view.line(y, text)
    local available, granted = q.os.capability("display.text")
    if available and granted then return q.display.text(0, y, text) end
    return false
end
function view.begin(choice)
    checked(q.ui.clear())
    if choice == "home-background" then
        checked(q.ui.wallpaper("assets/home-background.png"))
    else
        checked(q.ui.background(choice == "forest" and 0x20382c or 0x111827))
    end
end
function view.icon(x, y)
    return checked(q.ui.image(x, y, "assets/system-settings-icon.png"))
end
function view.label(x, y, text)
    return checked(q.ui.label(x, y, text))
end
function view.button(x, y, text, width)
    return checked(q.ui.button(x, y, text, width))
end
return view
