from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from backend.config import settings

_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
_EXPECTED_KEY: str = settings.aurax_api_key


def require_api_key(x_api_key: str | None = Security(_scheme)) -> str:
    if x_api_key != _EXPECTED_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key
