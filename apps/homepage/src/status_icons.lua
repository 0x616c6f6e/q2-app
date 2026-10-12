-- Status artwork supplied by the product designer; keep unknown distinct from zero/false.
local M = {}
function M.wifi(connected, rssi, enabled)
    if enabled == false then return "wifi-off" end
    if connected == nil then return nil end
    if not connected then return "wifi-disconnected" end
    if rssi == nil then return nil end -- Connected without a valid RSSI has no honest strength icon.
    return rssi >= -60 and "wifi-strong" or rssi >= -75 and "wifi-medium" or "wifi-weak"
end
function M.ble(connected, state)
    if state == "off" or state == "idle" or state == "pairing" or state == "connected" then
        return "ble-" .. state
    end
    if connected == nil then return nil end
    return connected and "ble-connected" or "ble-idle"
end
function M.battery(percent, charging)
    if percent == nil then return nil end
    local level = percent == 0 and 0 or percent <= 25 and 25 or percent <= 50 and 50 or percent <= 75 and 75 or 100
    return "battery-" .. (charging == true and "charging-" or "") .. level
end
return M
