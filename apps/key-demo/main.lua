-- Named action viewer: the SoC recognizes gestures; the APP owns their meaning.
local q = require("q2")
local names, states, labels, topics = {}, {}, {}, {}
local total, page = 0, 1
local actions = {[0] = "NONE", "SINGLE", "DOUBLE", "LONG"}
local last, counter, home, more, logging
local function checked(value, err)
    if value == nil then error(err.code) end
    return value
end
local function caption(name)
    return name .. "   " .. actions[states[name]]
end
local function render()
    checked(q.ui.clear())
    labels, home, more = {}, nil, nil
    local w, h = checked(q.ui.width()), checked(q.ui.height())
    if w < 240 or h < 280 then
        checked(q.ui.label(4, 4, "Key Demo"))
        counter, last = nil, nil
        return
    end
    checked(q.ui.label(0, 24, "Key Demo", "center"))
    counter = checked(q.ui.label(24, 70, "Events: " .. total .. " / Keys: " .. #names))
    last = checked(q.ui.label(24, 108, "Waiting for key input"))
    local rows = math.max(1, math.floor((h - 226) / 28))
    local pages = math.max(1, math.ceil(#names / rows))
    page = math.min(page, pages)
    for row = 1, rows do
        local name = names[(page - 1) * rows + row]
        if name then labels[name] = checked(q.ui.label(24, 150 + (row - 1) * 28, caption(name))) end
    end
    local available, granted = q.os.capability("apps.navigate")
    if available and granted then home = checked(q.ui.button(24, h - 64, "Home", 96)) end
    if pages > 1 then more = checked(q.ui.button(w - 120, h - 64, "More", 96)) end
end
return {
    on_start = function()
        local data_available, data_granted = q.os.capability("data.read")
        local count = checked(q.keys.count())
        -- The data contract allows 16 subscriptions per APP; larger diagnostic key sets use legacy watch.
        local generic = data_available and data_granted and count <= 16
        if not generic then checked(q.keys.watch(true)) end
        for i = 1, count do
            local name = checked(q.keys.name(i))
            names[#names + 1], states[name] = name, checked(q.keys.last(name))
            if generic then
                local key = "input.key." .. name .. ".action"
                checked(q.data.subscribe(key))
                topics[key] = name
            end
        end
        local available, granted = q.os.capability("system.log")
        logging = available and granted
        render()
    end,
    on_event = function(event)
        -- The data path already passed lifecycle lock/focus filtering; retain the standalone legacy path.
        if event.type == "data.event" and event.valid and topics[event.key] then
            event.type, event.text = "key.action", topics[event.key]
        end
        if event.type == "ui.resize" then render(); return end
        if event.type == "key.action" and states[event.text] ~= nil then
            -- Count every recognized action, including repeated actions of the same type.
            total = total + 1
            states[event.text] = event.value
            if counter then checked(q.ui.set_text(counter, "Events: " .. total .. " / Keys: " .. #names)) end
            if last then checked(q.ui.set_text(last, "Last: " .. caption(event.text))) end
            if labels[event.text] then checked(q.ui.set_text(labels[event.text], caption(event.text))) end
            if logging then checked(q.os.log("info", "KEY " .. event.text .. "=" .. actions[event.value] .. " total=" .. total)) end
        elseif event.type == "ui.click" then
            if event.value == home then checked(q.os.exit())
            elseif event.value == more then
                local rows = math.max(1, math.floor((q.ui.height() - 226) / 28))
                page = page % math.max(1, math.ceil(#names / rows)) + 1
                render()
            end
        end
    end,
}
