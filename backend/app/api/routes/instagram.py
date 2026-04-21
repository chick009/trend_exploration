from __future__ import annotations

from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.services.ingestion.instagram_client import (
    DEFAULT_FEED_TYPE,
    normalize_tikhub_data,
    pagination_hints,
    run_instagram_fetch_clean_save,
)

router = APIRouter(prefix="/instagram/hashtag", tags=["instagram"])


def _require_tikhub_key() -> None:
    if not get_settings().tikhub_api_key:
        raise HTTPException(
            status_code=503,
            detail="TIKHUB_API_KEY is not configured; Instagram hashtag search is unavailable.",
        )


@router.get("/search")
def search_instagram_hashtag_posts(
    keyword: str = Query(..., description="Hashtag keyword"),
    feed_type: Literal["top", "recent"] = Query(DEFAULT_FEED_TYPE, description="Instagram feed type"),
) -> dict[str, Any]:
    _require_tikhub_key()
    try:
        envelope, posts, saved_count = run_instagram_fetch_clean_save(
            keyword=keyword,
            feed_type=feed_type,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"TikHub request failed: {exc}") from exc

    data_obj = normalize_tikhub_data(envelope)
    body: dict[str, Any] = {
        "posts": posts,
        "saved_count": saved_count,
        "pagination": pagination_hints(envelope, data_obj),
    }
    if "code" in envelope:
        body["code"] = envelope["code"]
    if "message" in envelope:
        body["message"] = envelope["message"]
    return body


@router.get("/search/raw")
def search_instagram_hashtag_posts_raw(
    keyword: str = Query(..., description="Hashtag keyword"),
    feed_type: Literal["top", "recent"] = Query(DEFAULT_FEED_TYPE, description="Instagram feed type"),
) -> dict[str, Any]:
    _require_tikhub_key()
    try:
        envelope, _posts, saved_count = run_instagram_fetch_clean_save(
            keyword=keyword,
            feed_type=feed_type,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"TikHub request failed: {exc}") from exc

    return {"saved_count": saved_count, "tikhub": envelope}
