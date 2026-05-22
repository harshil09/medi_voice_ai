from fastapi import FastAPI
from database import ensure_emergency_column
from routers import doctor, vapi_webhook

app = FastAPI(title="Medical Care Hospital API", version="1.0")


@app.on_event("startup")
def migrate_schema():
    ensure_emergency_column()

app.include_router(doctor.router)
app.include_router(vapi_webhook.router)


@app.get("/")
def root():
    return {
        "app": "Medical Care Hospital API",
        "health": "/health",
        "vapi_webhook": "/vapi/webhook",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
