-- Bounded JSON POST client; never log request bodies, QR keys, cookies or signed media URLs.
local q = require("q2")
local config = require("config")
local M = {request = nil, now = 0}
function M.allowed(cap)
    local available, granted = q.os.capability(cap)
    return available and granted
end
local function quote(text)
    local out, chunk = {}, '"'
    for i = 1, #text do
        local ch, byte = string.sub(text, i, i), string.byte(text, i)
        if ch == '"' or byte == 92 then ch = string.char(92) .. ch
        elseif byte == 10 then ch = string.char(92) .. 'n'
        elseif byte == 13 then ch = string.char(92) .. 'r'
        elseif byte == 9 then ch = string.char(92) .. 't'
        elseif byte < 32 then return nil end
        chunk = chunk .. ch
        if #chunk >= 128 then out[#out + 1] = chunk; chunk = "" end
    end
    out[#out + 1] = chunk .. '"'
    return table.concat(out)
end
local pending
function M.active() return pending ~= nil or M.request ~= nil end
function M.close()
    pending, M.callback = nil, nil
    if M.request then q.network.close(M.request); M.request = nil end
end
function M.start(path, fields, cookie, callback)
    M.close()
    if not M.allowed("network.http") or not q.network.post then return nil, "Network unavailable" end
    fields = fields or {}
    fields.timestamp, fields.cookie = M.now, cookie or ""
    local items = {}
    for key, value in pairs(fields) do items[#items + 1] = {key, value} end
    pending = {path = path, items = items, index = 1, offset = 1, parts = {}, stage = "encode"}
    M.callback = callback
    return true
end
local function failed(err)
    local callback = M.callback
    M.close()
    callback(nil, nil, err or "unknown")
end
function M.tick(now)
    M.now = now
    if pending then
        local p, err = pending, nil
        if p.stage == "encode" then
            local item = p.items[p.index]
            if item then
                local key, value = item[1], item[2]
                if p.offset == 1 then
                    p.parts[#p.parts + 1] = (p.index > 1 and "," or "{") .. quote(key) .. ":"
                end
                if type(value) == "string" then
                    -- Bound escaping work even for the largest accepted session cookie.
                    local part = quote(string.sub(value, p.offset, p.offset + 511))
                    if not part then failed("Invalid request text"); return true end
                    p.parts[#p.parts + 1] = (p.offset == 1 and '"' or "") .. string.sub(part, 2, -2)
                    p.offset = p.offset + 512
                    if p.offset <= #value then return true end
                    p.parts[#p.parts + 1] = '"'
                else p.parts[#p.parts + 1] = tostring(value) end
                p.index, p.offset = p.index + 1, 1
            else
                p.body = table.concat(p.parts) .. "}"
                p.parts, p.items = nil, nil
                if #p.body > 8192 then failed("Request too large"); return true end
                p.stage = "open"
            end
        elseif p.stage == "open" then
            -- Cache keys ignore POST bodies: vary the URL, never expose credentials there.
            local url = config.base_url .. p.path .. "?timestamp=" .. now
            M.request, err = q.network.post(url, config.timeout_ms)
            if not M.request then failed(err and err.code); return true end
            p.stage = "upload"
        elseif p.stage == "upload" then
            for i = 1, 4 do
                if p.offset > #p.body then p.stage = "send"; break end
                local ok
                ok, err = q.network.write(M.request, string.sub(p.body, p.offset, p.offset + 254))
                if not ok then failed(err and err.code); return true end
                p.offset = p.offset + 255
            end
        else
            local ok
            ok, err = q.network.send(M.request)
            if not ok then failed(err and err.code); return true end
            pending = nil
        end
        return true
    end
    if not M.request then return false end
    local status, err = q.network.status(M.request)
    if status == "pending" then return false end
    local id, callback = M.request, M.callback
    M.request, M.callback = nil, nil
    callback(status and id or nil, status and q.network.code(id) or nil, err and err.code)
    q.network.close(id)
    return true -- Caller starts any follow-up on a later tick, after releasing the request quota.
end
function M.value(id, path)
    return q.network.json(id, path)
end
function M.long(id, path, maximum)
    local parts, length = {}, 0
    while length <= maximum do
        local chunk = q.network.json(id, path, length)
        if type(chunk) ~= "string" then return nil end
        length = length + #chunk
        if length > maximum then return nil end
        parts[#parts + 1] = chunk
        if #chunk < 255 then return table.concat(parts) end
    end
    return nil
end
return M
