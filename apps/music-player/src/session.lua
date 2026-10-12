-- Fragmented sessions: commit metadata last; incomplete writes cannot restore a login.
local q = require("q2")
local api = require("api")
local config = require("config")
local M = {error = nil, state = "idle"}
local MAX_BYTES, MAX_PARTS = 4096, 17
local writes, cursor, saving = {}, 1, false
local loading, clearing = nil, nil
local function fault(err)
    M.error, M.state = err and err.code or "io_error", "error"
    writes, loading, clearing = {}, nil, nil
    return false, true
end
local function read(key)
    local text, err = q.storage.get(key)
    if text == nil and err and err.code ~= "not_found" then fault(err) end
    return text
end
function M.pending() return writes[cursor] ~= nil or clearing ~= nil end
function M.tick()
    if clearing then
        local stage, erase = clearing.stage, clearing.erase
        if not api.allowed("storage.private") then clearing = nil; return false, true, nil, true end
        if stage == 0 or erase then
            local key = stage == 0 and "ncm_count" or "ncm_cookie_" .. stage
            local ok, err = q.storage.put(key, stage == 0 and "0" or "")
            if not ok then fault(err); return false, true, nil, false end
            clearing.stage, clearing.erase = stage + 1, false
        else
            local chunk, err = q.storage.get("ncm_cookie_" .. stage)
            if chunk == nil and err and err.code ~= "not_found" then
                fault(err); return false, true, nil, false
            end
            if chunk and chunk ~= "" then clearing.erase = true else clearing.stage = stage + 1 end
        end
        if clearing.stage > MAX_PARTS then clearing = nil; M.state = "empty"; return false, true, nil, true end
        return nil, true
    end
    local item = writes[cursor]
    if not item and loading then
        local stage = loading.stage
        if not api.allowed("storage.private") then loading = nil; return nil, true, "" end
        local key = stage == 0 and "ncm_base" or stage == 1 and "ncm_count" or "ncm_cookie_" .. (stage - 1)
        local text = read(key)
        if M.error then return nil, true end -- I/O failure must not erase saved credentials.
        if stage == 0 then
            if text ~= config.base_url then loading = nil; M.state = "empty"; return nil, true, "" end
        elseif stage == 1 then
            local count = tonumber(text or "0")
            if count == 0 then loading = nil; M.state = "empty"; return nil, true, "" end
            if not count or count < 1 or count > MAX_PARTS or count % 1 ~= 0 then
                return fault({code = "invalid_format"})
            end
            loading.count = count
        else
            if not text or text == "" then return fault({code = "invalid_format"}) end
            loading.parts[#loading.parts + 1] = text
            if stage - 1 == loading.count then
                local cookie = table.concat(loading.parts)
                loading = nil
                if #cookie > MAX_BYTES then return fault({code = "quota_exceeded"}) end
                M.state = "restored"
                return nil, true, cookie
            end
        end
        loading.stage = stage + 1
        return nil, true
    end
    if not item then return nil, false end
    -- One storage call per tick.
    local ok, err = q.storage.put(item[1], item[2])
    if not ok then return fault(err) end
    cursor = cursor + 1
    if cursor > #writes then writes = {}; M.state = "saved"; return saving, true end
    return nil, true
end
function M.clear()
    M.error, M.state = nil, "clearing"
    -- Invalidate first, then probe/erase existing fragments without exceeding the file quota.
    loading = nil
    writes, cursor, saving = {}, 1, false
    clearing = {stage = 0}
end
function M.begin_load()
    M.error, M.state = nil, "loading"
    -- Load metadata and fragments on separate ticks.
    clearing = nil
    writes, cursor, saving = {}, 1, false
    loading = {stage = 0, parts = {}}
end
function M.save(cookie)
    M.error, M.state = nil, "saving"
    loading, clearing = nil, nil
    writes, cursor, saving = {}, 1, true
    if not api.allowed("storage.private") then fault({code = "permission_denied"}); return false end
    if #cookie == 0 or #cookie > MAX_BYTES then fault({code = "quota_exceeded"}); return false end
    writes[1] = {"ncm_count", "0"}
    local count = math.ceil(#cookie / 255)
    for i = 1, count do
        writes[#writes + 1] = {"ncm_cookie_" .. i, string.sub(cookie, (i - 1) * 255 + 1, i * 255)}
    end
    writes[#writes + 1] = {"ncm_base", config.base_url}
    writes[#writes + 1] = {"ncm_count", tostring(count)}
    return false -- Only the final metadata commit confirms persistence.
end
return M
