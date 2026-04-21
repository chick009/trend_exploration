from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.services.ingestion.tiktok_photo_client import (
    normalize_tikhub_data,
    pagination_hints,
    run_tiktok_photo_fetch_clean_save,
)

router = APIRouter(prefix="/tiktok/photos", tags=["tiktok"])


def _require_tikhub_key() -> None:
    if not get_settings().tikhub_api_key:
        raise HTTPException(
            status_code=503,
            detail="TIKHUB_API_KEY is not configured; TikTok photo search is unavailable.",
        )


@router.get("/search")
def search_tiktok_photos(
    keyword: str = Query(..., description="Search keyword"),
    count: int = Query(20, ge=1, le=50, description="Results per page"),
    offset: int = Query(0, ge=0, description="Page offset / cursor seed"),
    search_id: str | None = Query(None, description="Search id from previous response for pagination"),
    cookie: str | None = Query(None, description="Optional TikTok web cookie"),
) -> dict[str, Any]:
    _require_tikhub_key()
    try:
        envelope, posts, saved_count = run_tiktok_photo_fetch_clean_save(
            keyword=keyword,
            count=count,
            offset=offset,
            search_id=search_id,
            cookie=cookie,
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
def search_tiktok_photos_raw(
    keyword: str = Query(..., description="Search keyword"),
    count: int = Query(20, ge=1, le=50, description="Results per page"),
    offset: int = Query(0, ge=0, description="Page offset / cursor seed"),
    search_id: str | None = Query(None, description="Search id from previous response for pagination"),
    cookie: str | None = Query(None, description="Optional TikTok web cookie"),
) -> dict[str, Any]:
    _require_tikhub_key()
    try:
        envelope, _posts, saved_count = run_tiktok_photo_fetch_clean_save(
            keyword=keyword,
            count=count,
            offset=offset,
            search_id=search_id,
            cookie=cookie,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"TikHub request failed: {exc}") from exc

    return {"saved_count": saved_count, "tikhub": envelope}
