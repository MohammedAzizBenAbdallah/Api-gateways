from fastapi import Request, HTTPException

async def kong_header_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    
    if not request.headers.get("kong-header"):
        raise HTTPException(status_code=403, detail="all requests should come from kong gateway")
    response = await call_next(request)
    return response

def verify_kong_header(request: Request):
    if request.method == "OPTIONS":
        return True
        
    if not request.headers.get("kong-header"):
        raise HTTPException(status_code=403, detail="all requests should come from kong gateway")
    return True
