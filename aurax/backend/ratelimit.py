from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared limiter instance. Defined in its own module so route modules can
# attach per-route limits (e.g. the tighter cap on /query) without importing
# from backend.main, which would create a circular import.
limiter = Limiter(key_func=get_remote_address, default_limits=["30/minute"])
