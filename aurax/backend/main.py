import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from backend.ratelimit import limiter
from backend.services import db
from backend.routes import query, yields, refresh

logger = logging.getLogger("aurax.refresh")

# Cap a single refresh so a slow/blocked RPC can't wedge the loop forever
# (the per-call timeout is 20s and we fan out across two chains + reserves).
_REFRESH_TIMEOUT = 180


async def _hourly_refresh():
    """Refresh live Aave data on startup and every hour."""
    from backend.services.data_refresh import refresh_reserves
    while True:
        try:
            n = await asyncio.wait_for(refresh_reserves(), timeout=_REFRESH_TIMEOUT)
            logger.info("refresh ok: %s reserves updated", n)
        except asyncio.TimeoutError:
            logger.warning("refresh timed out after %ss", _REFRESH_TIMEOUT)
        except Exception:
            logger.exception("refresh failed")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.ensure_db_initialized()  # seed an empty persistent volume on first boot
    await db.get_db()
    asyncio.create_task(_hourly_refresh())
    yield
    await db.close_db()


app = FastAPI(
    title="AuraX — DeFi Yield Intelligence",
    description="Aave v3 Polygon — NL querying, live yields, risk-adjusted ranking",
    version="0.2.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Required for default_limits to apply to all routes — without this middleware
# the limiter is inert and every endpoint is unthrottled.
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router)
app.include_router(yields.router)
app.include_router(refresh.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


_FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "index.html"


@app.get("/", include_in_schema=False)
async def index():
    """Serve the static terminal UI (calls /query and /yields on this host)."""
    return FileResponse(_FRONTEND)
