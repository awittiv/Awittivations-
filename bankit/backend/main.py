from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import webhook, loans, merchants, scoring_api, linkedin_webhook, admin

app = FastAPI(title="Bankit API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://launchlayer.app"],
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


@app.get("/health")
async def health():
    return {"status": "ok"}
