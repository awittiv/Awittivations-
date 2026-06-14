import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import webhook, loans, merchants, scoring_api, linkedin_webhook, admin, payments

app = FastAPI(title="Bankit API", version="0.1.0")

_allowed_origins = [
    "http://localhost:3000",
    "https://launchlayer.app",
]
if _frontend_url := os.getenv("FRONTEND_URL"):
    _allowed_origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook.router)
app.include_router(loans.router)
app.include_router(merchants.router)
app.include_router(scoring_api.router)
app.include_router(linkedin_webhook.router)
app.include_router(admin.router)
app.include_router(payments.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
