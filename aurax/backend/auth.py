import os
from fastapi import Header, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(x_api_key: str | None = Security(_scheme)) -> str:
    expected = os.environ.get("AURAX_API_KEY", "")
    if not expected:
        raise HTTPException(status_code=500, detail="Server not configured")
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key
