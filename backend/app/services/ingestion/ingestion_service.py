from __future__ import annotations

import logging
from collections import Counter
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.db.repository import (
    create_ingestion_run,
    update_ingestion_run,
    upsert_search_trend,
)
from app.models.schemas import IngestionRunRequest
from app.services.ingestion.llm_enrichment import LLMEnrichmentService
from app.services.ingestion.instagram_client import InstagramClient, run_instagram_fetch_clean_save
from app.services.ingestion.sales_seed import SalesSeedService
from app.services.ingestion.serpapi_client import SerpApiClient
from app.services.ingestion.source_capabilities import build_recency_support
from app.services.ingestion.tiktok_photo_client import TikTokPhotoClient, run_tiktok_photo_fetch_clean_save

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.serpapi_client = SerpApiClient()
        self.tiktok_photo_client = TikTokPhotoClient()
        self.instagram_client = InstagramClient()
        self.sales_seed_service = SalesSeedService()
        self.enrichment_service = LLMEnrichmentService()

    def create_run(self, request: IngestionRunRequest) -> tuple[str, str]:
        run_id = str(uuid4())
        batch_id = f"batch-{uuid4()}"
        create_ingestion_run(run_id, batch_id, request)
        return run_id, batch_id

    def run(self, run_id: str, batch_id: str, request: IngestionRunRequest) -> None:
        recency_support = [item.model_dump(mode="json") for item in build_recency_support(request.sources)]
        update_ingestion_run(
            run_id,
            status="running",
            stats={"phase": "starting"},
            recency_support=recency_support,
        )
        guardrail_flags: list[str] = []
        stats = Counter()
        target_keywords = list(request.target_keywords)
        if request.recent_days is not None:
            guardrail_flags.extend(
                item["detail"]
                for item in recency_support
                if item["status"] != "supported"
            )
        try:
            if "google_trends" in request.sources:
                for row in self.serpapi_client.fetch_trends(
                    market=request.market,
                    category=request.category,
                    recent_days=request.recent_days or 7,
                    seed_terms=target_keywords,
                ):
                    enrichment = self.enrichment_service.enrich_keyword(
                        row["keyword"],
                        category_hint=request.category,
                    )
                    row.update(
                        {
                            "llm_category": enrichment.llm_category,
                            "llm_subcategory": enrichment.llm_subcategory,
                            "relevance_score": enrichment.relevance_score,
                            "processed_at": enrichment.processed_at,
                            "source_batch_id": batch_id,
                        }
                    )
                    upsert_search_trend(row)
                    stats["search_rows"] += 1

            if "sales" in request.sources:
                sales_stats = self.sales_seed_service.refresh()
                stats.update(sales_stats)

            if "tiktok" in request.sources:
                if not self.settings.tikhub_api_key:
                    guardrail_flags.append("TikTok photo search skipped: TIKHUB_API_KEY is not set.")
                else:
                    photo_page_size = request.tiktok_photo_count_per_keyword if request.tiktok_photo_count_per_keyword is not None else 10
                    photo_page_size = min(max(photo_page_size, 1), 50)
                    for term in target_keywords:
                        try:
                            _, _, saved = run_tiktok_photo_fetch_clean_save(
                                keyword=term,
                                count=photo_page_size,
                                offset=0,
                                client=self.tiktok_photo_client,
                                source_batch_id=batch_id,
                            )
                            stats["tiktok_rows"] += saved
                        except (httpx.HTTPError, RuntimeError) as exc:
                            logger.warning("TikTok photo fetch failed for term %r: %s", term, exc)
                            guardrail_flags.append(f"TikTok photo fetch failed for '{term}': {exc}")

            if "instagram" in request.sources:
                if not self.settings.tikhub_api_key:
                    guardrail_flags.append("Instagram hashtag search skipped: TIKHUB_API_KEY is not set.")
                else:
                    for term in target_keywords:
                        try:
                            _, _, saved = run_instagram_fetch_clean_save(
                                keyword=term,
                                feed_type=request.instagram_feed_type,
                                client=self.instagram_client,
                                source_batch_id=batch_id,
                            )
                            stats["instagram_rows"] += saved
                            if saved == 0:
                                guardrail_flags.append(
                                    "Instagram hashtag search returned no posts for "
                                    f"'{term}'. Phrase-like keywords can miss a hashtag-only endpoint."
                                )
                        except (httpx.HTTPError, RuntimeError) as exc:
                            logger.warning("Instagram hashtag fetch failed for term %r: %s", term, exc)
                            guardrail_flags.append(f"Instagram hashtag fetch failed for '{term}': {exc}")

            if (
                stats["search_rows"] == 0
                and stats["tiktok_rows"] == 0
                and stats["instagram_rows"] == 0
            ):
                guardrail_flags.append("No external rows were ingested; using only existing or synthetic sales data.")
            stats["sources_count"] = len(request.sources)
            stats["target_keywords_count"] = len(target_keywords)
            stats["target_keywords"] = list(target_keywords)
            stats["recency_support"] = recency_support
            stats["sources_honoring_recency"] = [item["source"] for item in recency_support if item["status"] == "supported"]
            stats["sources_partial_recency"] = [item["source"] for item in recency_support if item["status"] == "partial"]
            stats["sources_ignoring_recency"] = [item["source"] for item in recency_support if item["status"] == "unsupported"]
            stats["limits"] = {
                "max_target_keywords": request.max_target_keywords,
                "tiktok_photo_count_per_keyword": request.tiktok_photo_count_per_keyword,
                "instagram_feed_type": request.instagram_feed_type,
            }
            update_ingestion_run(
                run_id,
                status="completed",
                stats={**dict(stats), "batch_id": batch_id},
                guardrail_flags=guardrail_flags,
                recency_support=recency_support,
            )
        except Exception as exc:
            update_ingestion_run(
                run_id,
                status="failed",
                stats=dict(stats),
                error_message=str(exc),
                guardrail_flags=guardrail_flags,
                recency_support=recency_support,
            )
            raise
