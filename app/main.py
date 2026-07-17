from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.database.init_db import init_database
from monitoring.app.health import health_router
from monitoring.app.logging import StructuredLoggingMiddleware
from monitoring.app.metrics import MetricsMiddleware, metrics_endpoint
from monitoring.app.opentelemetry import setup_opentelemetry

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

app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(MetricsMiddleware)

app.include_router(chat_router)
app.include_router(health_router)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def root():
    return FileResponse(str(static_dir / "index.html"))


@app.get("/chat")
def chat_redirect():
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/")


@app.get("/index.html")
def index_html():
    return FileResponse(str(static_dir / "index.html"))


@app.on_event("startup")
def on_startup():
    init_database()
    setup_opentelemetry(app)


@app.get("/metrics")
def metrics(request: Request):
    return metrics_endpoint(request)
