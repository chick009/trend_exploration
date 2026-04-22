from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.analysis import router as analysis_router
from app.api.routes.db_browser import router as db_browser_router
from app.api.routes.health import router as health_router
from app.api.routes.instagram import router as instagram_router
from app.api.routes.ingestion import router as ingestion_router
from app.api.routes.tiktok_photo import router as tiktok_photo_router
from app.core.config import get_settings
from app.db.bootstrap import seed_reference_data, seed_sales_data
from app.db.migrator import apply_migrations
from app.services.ingestion.scheduler import build_scheduler

settings = get_settings()
scheduler = build_scheduler() if settings.enable_scheduler else None
cors_origins = settings.parsed_cors_origins()
allow_credentials = settings.cors_allow_credentials and "*" not in cors_origins


@asynccontextmanager
async def lifespan(_: FastAPI):
    apply_migrations()
    seed_reference_data()
    seed_sales_data()
    if scheduler and not scheduler.running:
        scheduler.start()
    yield
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ingestion_router)
app.include_router(analysis_router)
app.include_router(db_browser_router)
app.include_router(health_router)
app.include_router(instagram_router)
app.include_router(tiktok_photo_router)
