local SimpleValidator = {
  PRIORITY = 1000,
  VERSION = "1.0",
}
function SimpleValidator:access(conf)
    -- 1 get the json body
    local body, err = kong.request.get_body()

    if not body then 
        return kong.response.exit(400, {message ="No Json body found"})
    end
    -- 2 check if required key is missing 
    if not body[conf.required_key] then 
        return kong.response.exit(400, {message ="Missing required key"})
    end 
end
return SimpleValidator        