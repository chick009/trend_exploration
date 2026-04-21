from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.models.schemas import IngestionRunRequest
from app.services.ingestion.ingestion_service import IngestionService


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    ingestion_service = IngestionService()

    def refresh_daily() -> None:
        request = IngestionRunRequest(
            market="HK",
            category="skincare",
            recent_days=7,
            sources=["rednote", "google_trends", "sales"],
        )
        run_id, batch_id = ingestion_service.create_run(request)
        ingestion_service.run(run_id, batch_id, request)

    scheduler.add_job(refresh_daily, "cron", hour=6, minute=0, id="daily_refresh", replace_existing=True)
    return scheduler
