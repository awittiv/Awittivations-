import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.services import db
from backend.routes import query, yields, refresh


async def _hourly_refresh():
    """Refresh live Aave data from DeFiLlama on startup and every hour."""
    from backend.services.data_refresh import refresh_reserves
    while True:
        try:
            await refresh_reserves()
        except Exception:
            pass
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
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
