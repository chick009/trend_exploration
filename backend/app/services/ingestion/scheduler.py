from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.models.schemas import IngestionRunRequest
from app.services.ingestion.ingestion_service import IngestionService


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    ingestion_service = IngestionService()

    def refresh_daily() -> None:
        default_keywords = ingestion_service.settings.default_seed_terms[:5]
        request = IngestionRunRequest(
            market="HK",
            category="skincare",
            recent_days=7,
            sources=["google_trends", "sales"],
            target_keywords=default_keywords,
            suggested_keywords=default_keywords,
        )
        run_id, batch_id = ingestion_service.create_run(request)
        ingestion_service.run(run_id, batch_id, request)

    scheduler.add_job(refresh_daily, "cron", hour=6, minute=0, id="daily_refresh", replace_existing=True)
    return scheduler
