"""FastAPI Data Explorer backend."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import documents

app = FastAPI(
    title="Silver Layer Data Explorer",
    description="Explore and inspect ETL-processed data in PostgreSQL",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "database": "connected"}
