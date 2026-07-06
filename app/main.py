from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text as sa_text

from app.api.chat import router as chat_router

app = FastAPI(
    title="Project 001 — AI Platform MVP",
    description="Chat with your knowledge base: events, communications, documents",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)

HEALTH_QUERY = sa_text("SELECT 1")


@app.get("/health")
def health():
    from app.database.session import SessionLocal
    try:
        with SessionLocal() as s:
            s.execute(HEALTH_QUERY)
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}
