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
    upsert_social_post,
)
from app.models.schemas import IngestionRunRequest
from app.services.ingestion.llm_enrichment import LLMEnrichmentService
from app.services.ingestion.instagram_client import InstagramClient, run_instagram_fetch_clean_save
from app.services.ingestion.rednote_client import RednoteClient
from app.services.ingestion.sales_seed import SalesSeedService
from app.services.ingestion.serpapi_client import SerpApiClient
from app.services.ingestion.tiktok_photo_client import TikTokPhotoClient, run_tiktok_photo_fetch_clean_save

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.serpapi_client = SerpApiClient()
        self.rednote_client = RednoteClient()
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
        update_ingestion_run(run_id, status="running", stats={"phase": "starting"})
        guardrail_flags: list[str] = []
        stats = Counter()
        seeds = (request.seed_terms or self.settings.default_seed_terms)[: request.max_seed_terms]
        try:
            if "google_trends" in request.sources:
                for row in self.serpapi_client.fetch_trends(
                    market=request.market,
                    category=request.category,
                    recent_days=request.recent_days or 7,
                    seed_terms=seeds,
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

            if "rednote" in request.sources:
                for row in self.rednote_client.fetch_posts(
                    market=request.market,
                    category=request.category,
                    recent_days=request.recent_days or 7,
                    seed_terms=seeds,
                    max_notes_per_keyword=request.max_notes_per_keyword,
                    max_comment_posts_per_keyword=request.max_comment_posts_per_keyword,
                    max_comments_per_post=request.max_comments_per_post,
                ):
                    enrichment = self.enrichment_service.enrich_text(
                        text=" ".join(
                            [
                                row.get("title", ""),
                                row.get("content_text", ""),
                                " ".join(row.get("hashtags", [])),
                                " ".join(row.get("comment_mentions", [])),
                            ]
                        ),
                        category_hint=request.category,
                        explicit_entities=row.get("entity_mentions", []),
                    )
                    row.update(
                        {
                            "entity_mentions": sorted(set(row.get("entity_mentions", [])) | set(enrichment.llm_entities)),
                            "llm_category": enrichment.llm_category,
                            "llm_subcategory": enrichment.llm_subcategory,
                            "positivity_score": enrichment.positivity_score,
                            "sentiment_label": enrichment.sentiment_label,
                            "relevance_score": enrichment.relevance_score,
                            "llm_entities": enrichment.llm_entities,
                            "llm_summary": enrichment.llm_summary,
                            "processed_at": enrichment.processed_at,
                            "processing_model": enrichment.processing_model,
                            "source_batch_id": batch_id,
                        }
                    )
                    upsert_social_post(row)
                    stats["social_rows"] += 1

            if "sales" in request.sources:
                sales_stats = self.sales_seed_service.refresh()
                stats.update(sales_stats)

            if "tiktok" in request.sources:
                if not self.settings.tikhub_api_key:
                    guardrail_flags.append("TikTok photo search skipped: TIKHUB_API_KEY is not set.")
                else:
                    photo_page_size = min(max(request.max_notes_per_keyword, 1), 50)
                    for term in seeds:
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
                    for term in seeds:
                        try:
                            _, _, saved = run_instagram_fetch_clean_save(
                                keyword=term,
                                feed_type="top",
                                client=self.instagram_client,
                                source_batch_id=batch_id,
                            )
                            stats["instagram_rows"] += saved
                        except (httpx.HTTPError, RuntimeError) as exc:
                            logger.warning("Instagram hashtag fetch failed for term %r: %s", term, exc)
                            guardrail_flags.append(f"Instagram hashtag fetch failed for '{term}': {exc}")

            if (
                stats["search_rows"] == 0
                and stats["social_rows"] == 0
                and stats["tiktok_rows"] == 0
                and stats["instagram_rows"] == 0
            ):
                guardrail_flags.append("No external rows were ingested; using only existing or synthetic sales data.")
            stats["sources_count"] = len(request.sources)
            stats["seed_terms_count"] = len(seeds)
            stats["limits"] = {
                "max_seed_terms": request.max_seed_terms,
                "max_notes_per_keyword": request.max_notes_per_keyword,
                "max_comment_posts_per_keyword": request.max_comment_posts_per_keyword,
                "max_comments_per_post": request.max_comments_per_post,
            }
            update_ingestion_run(
                run_id,
                status="completed",
                stats={**dict(stats), "batch_id": batch_id},
                guardrail_flags=guardrail_flags,
            )
        except Exception as exc:
            update_ingestion_run(
                run_id,
                status="failed",
                stats=dict(stats),
                error_message=str(exc),
                guardrail_flags=guardrail_flags,
            )
            raise
