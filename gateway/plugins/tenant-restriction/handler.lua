local cjson = require "cjson"

local TenantRestriction = {
  PRIORITY = 900,
  VERSION = "2.0", -- Version bump
}

local function decode_base64(data)
  local b = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
  data = string.gsub(data, '[^' .. b .. '=]', '')
  return (data:gsub('.', function(x)
    if (x == '=') then return '' end
    local r, f = '', (b:find(x) - 1)
    for i = 6, 1, -1 do r = r .. (f % 2 ^ i - f % 2 ^ (i - 1) > 0 and '1' or '0') end
    return r;
  end):gsub('%d%d%d%d%d%d%d%d', function(x)
    local c = 0
    for i = 1, 8 do c = c + (x:sub(i, i) == '1' and 2 ^ (8 - i) or 0) end
    return string.char(c)
  end))
end

function TenantRestriction:access(conf)
  local auth_header = kong.request.get_header("Authorization")
  if not auth_header then
    return kong.response.exit(401, { message = "Unauthorized: No token provided" })
  end

  local token = auth_header:gsub("Bearer ", "")
  local _, payload_b64 = token:match("([^.]+).([^.]+).([^.]+)")

  if not payload_b64 then
    return kong.response.exit(401, { message = "Unauthorized: Invalid token format" })
  end

  -- Base64 Padding and Sanitization
  while #payload_b64 % 4 ~= 0 do payload_b64 = payload_b64 .. "=" end
  payload_b64 = payload_b64:gsub("-", "+"):gsub("_", "/")

  local ok, payload_json = pcall(decode_base64, payload_b64)
  if not ok then
      kong.log.err("Failed to decode JWT base64")
    return kong.response.exit(401, { message = "Unauthorized: Failed to decode token" })
  end
  
  -- Clean up payload string
  payload_json = payload_json:match("^%s*(.-)%s*$")
  payload_json = payload_json:match("(.*})")

  local ok, claims = pcall(cjson.decode, payload_json)
  if not ok then
      kong.log.err("Failed to parse JWT JSON: ", payload_json)
    return kong.response.exit(401, { message = "Unauthorized: Failed to parse token JSON" })
  end

  -- Extract Tenant ID
  -- We check for 'tenant_id' as a top-level claim (mapped from Keycloak group attributes)
  local tenant_id = claims.tenant_id or (claims.realm_access and claims.realm_access.tenant_id)
  
  if not tenant_id then
    kong.log.warn("No tenant_id found in token")
    return kong.response.exit(403, { message = "Forbidden: No tenant_id found in token. Please contact administrator." })
  end

  -- Set the X-Tenant-ID header for the upstream (Backend/Orchestrator)
  kong.service.request.set_header("X-Tenant-ID", tenant_id)
  
  -- We also set a log header for visibility
  kong.response.set_header("X-Authenticated-Tenant", tenant_id)
end

return TenantRestriction
