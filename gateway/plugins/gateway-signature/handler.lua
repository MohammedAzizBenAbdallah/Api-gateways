-- Signs upstream requests so FastAPI can verify traffic originated from Kong (ORK-025).
-- Pure HMAC-SHA256 using resty.sha256 (no resty.openssl dependency).

local sha256 = require("resty.sha256")
local bit = require("bit")
local bxor = bit.bxor
local uuid = require("kong.tools.utils").uuid

local function hmac_sha256_binary(key, text)
  local block = 64
  if #key > block then
    local x = sha256:new()
    x:update(key)
    key = x:final()
  end
  if #key < block then
    key = key .. string.rep(string.char(0), block - #key)
  end
  local ipad = {}
  local opad = {}
  for i = 1, block do
    local kb = string.byte(key, i)
    ipad[i] = string.char(bxor(kb, 0x36))
    opad[i] = string.char(bxor(kb, 0x5c))
  end
  ipad = table.concat(ipad)
  opad = table.concat(opad)
  local inner = sha256:new()
  inner:update(ipad .. text)
  local inner_digest = inner:final()
  local outer = sha256:new()
  outer:update(opad .. inner_digest)
  return outer:final()
end

local GatewaySignature = {
  PRIORITY = 30000,
  VERSION = "1.0",
}

function GatewaySignature:access(conf)
  if not conf or not conf.secret or conf.secret == "" then
    kong.log.err("gateway-signature: missing secret")
    return kong.response.exit(500, { message = "gateway signature not configured" })
  end

  local ts = tostring(ngx.time())
  -- Kong 3.9 PDK has no kong.request.get_id(); UUID is unique per request for replay protection.
  local nonce = uuid()
  local method = kong.request.get_method()
  local path = kong.request.get_path()
  local payload = table.concat({ method, path, ts, nonce }, "|")

  local digest = hmac_sha256_binary(conf.secret, payload)
  local sig = ngx.encode_base64(digest)

  kong.service.request.set_header("X-Gateway-Timestamp", ts)
  kong.service.request.set_header("X-Gateway-Nonce", nonce)
  kong.service.request.set_header("X-Gateway-Signature", sig)
end

return GatewaySignature
