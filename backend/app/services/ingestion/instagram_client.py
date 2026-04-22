from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.db.repository import upsert_instagram_posts

logger = logging.getLogger(__name__)


FETCH_HASHTAG_POSTS_PATH = "/api/v1/instagram/v2/fetch_hashtag_posts"
REQUEST_TIMEOUT_SECONDS = 45
MAX_RETRIES = 3
DEFAULT_FEED_TYPE = "top"
GENERIC_HASHTAG_TOKENS = {
    "and",
    "beauty",
    "care",
    "cleanser",
    "cream",
    "essence",
    "for",
    "gel",
    "lotion",
    "mask",
    "of",
    "oil",
    "repair",
    "serum",
    "skin",
    "skincare",
    "solution",
    "spf",
    "sun",
    "toner",
    "wash",
    "with",
}


def normalize_tikhub_data(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw = payload.get("data")
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw if isinstance(raw, dict) else None


def _extract_items(data_obj: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not data_obj:
        return []

    nested = data_obj.get("data")
    if isinstance(nested, dict):
        items = nested.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]

    items = data_obj.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def extract_instagram_posts(api_response: dict[str, Any]) -> list[dict[str, Any]]:
    data_obj = normalize_tikhub_data(api_response)
    items = _extract_items(data_obj)

    posts: list[dict[str, Any]] = []
    for item in items:
        post_id = item.get("id")
        if post_id in (None, ""):
            continue

        user = item.get("user") or {}
        if not isinstance(user, dict):
            user = {}

        location = item.get("location") or {}
        if not isinstance(location, dict):
            location = {}

        hashtags = [tag.lstrip("#") for tag in item.get("caption_hashtags", []) if isinstance(tag, str)]
        mentions = [mention.lstrip("@") for mention in item.get("caption_mentions", []) if isinstance(mention, str)]

        posts.append(
            {
                "post_id": str(post_id),
                "code": item.get("code"),
                "username": user.get("username"),
                "full_name": user.get("full_name"),
                "caption": item.get("caption_text"),
                "hashtags": hashtags,
                "mentions": mentions,
                "likes": item.get("like_count", 0),
                "comments": item.get("comment_count", 0),
                "views": item.get("play_count", 0),
                "is_video": bool(item.get("is_video", False)),
                "created_at": item.get("taken_at"),
                "location_name": location.get("name"),
                "city": location.get("city"),
                "lat": location.get("lat"),
                "lng": location.get("lng"),
            }
        )

    return posts


def pagination_hints(_api_response: dict[str, Any], data_obj: dict[str, Any] | None) -> dict[str, Any]:
    if not data_obj:
        return {}

    hints: dict[str, Any] = {}
    nested = data_obj.get("data")
    for container in (nested, data_obj):
        if isinstance(container, dict) and container.get("has_more") is not None:
            hints["has_more"] = container.get("has_more")
            break
    return hints


def cleaned_posts_to_db_rows(
    posts: list[dict[str, Any]],
    *,
    search_keyword: str,
    source_batch_id: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for post in posts:
        post_id = post.get("post_id")
        if post_id in (None, ""):
            continue

        rows.append(
            {
                "post_id": str(post_id),
                "search_keyword": search_keyword,
                "code": post.get("code"),
                "username": post.get("username"),
                "full_name": post.get("full_name"),
                "caption": post.get("caption"),
                "hashtags_json": json.dumps(post.get("hashtags") or []),
                "mentions_json": json.dumps(post.get("mentions") or []),
                "likes": int(post.get("likes") or 0),
                "comments": int(post.get("comments") or 0),
                "views": int(post.get("views") or 0),
                "is_video": 1 if post.get("is_video") else 0,
                "created_at": post.get("created_at"),
                "location_name": post.get("location_name"),
                "city": post.get("city"),
                "lat": post.get("lat"),
                "lng": post.get("lng"),
                "source_batch_id": source_batch_id,
            }
        )
    return rows


def build_hashtag_keyword_candidates(keyword: str) -> list[str]:
    trimmed = keyword.strip().lstrip("#")
    if not trimmed:
        return []

    tokens = [token.casefold() for token in re.findall(r"[A-Za-z0-9_]+", trimmed)]
    compact = "".join(tokens)
    filtered_tokens = [token for token in tokens if token not in GENERIC_HASHTAG_TOKENS]
    compact_filtered = "".join(filtered_tokens)

    candidates: list[str] = []
    for candidate in (
        trimmed,
        compact,
        compact_filtered,
        filtered_tokens[0] if filtered_tokens else "",
    ):
        value = candidate.strip()
        if value and value not in candidates:
            candidates.append(value)
    return candidates


class InstagramClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def _drop_empty_params(params: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in params.items() if value is not None and value != ""}

    def _request_json(
        self,
        client: httpx.Client,
        path: str,
        *,
        params: dict[str, Any],
        context: str,
    ) -> dict[str, Any]:
        last_exception: httpx.HTTPError | None = None
        params = self._drop_empty_params(params)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = client.get(path, params=params)
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, dict) else {}
            except httpx.HTTPStatusError as exc:
                last_exception = exc
                status_code = exc.response.status_code
                if status_code == 400:
                    logger.warning(
                        "TikHub rejected %s with 400. response=%s",
                        context,
                        exc.response.text[:500],
                    )
                if status_code < 500 or attempt == MAX_RETRIES:
                    raise
            except httpx.RequestError as exc:
                last_exception = exc
                if attempt == MAX_RETRIES:
                    raise

            logger.warning(
                "TikHub Instagram request retry %s/%s for %s",
                attempt,
                MAX_RETRIES,
                context,
            )
            time.sleep(min(attempt, 3))

        if last_exception is not None:
            raise last_exception
        return {}

    def fetch_hashtag_posts(
        self,
        *,
        keyword: str,
        feed_type: str = DEFAULT_FEED_TYPE,
    ) -> dict[str, Any]:
        if not self.settings.tikhub_api_key:
            raise RuntimeError("TIKHUB_API_KEY is not configured")

        headers = {"Authorization": f"Bearer {self.settings.tikhub_api_key}"}
        normalized_keyword = keyword.strip().lstrip("#")
        params: dict[str, Any] = {
            "keyword": normalized_keyword,
            "feed_type": feed_type,
        }

        with httpx.Client(
            base_url="https://api.tikhub.io",
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as client:
            return self._request_json(
                client,
                FETCH_HASHTAG_POSTS_PATH,
                params=params,
                context=f"fetch_hashtag_posts keyword={normalized_keyword!r} feed_type={feed_type!r}",
            )


def run_instagram_fetch_clean_save(
    *,
    keyword: str,
    feed_type: str = DEFAULT_FEED_TYPE,
    client: InstagramClient | None = None,
    source_batch_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    """
    Fetch from TikHub, extract posts, and upsert into instagram_posts.
    Returns (envelope, posts, saved_count).
    """
    c = client or InstagramClient()
    attempted_keywords = build_hashtag_keyword_candidates(keyword)
    envelope: dict[str, Any] = {}
    posts: list[dict[str, Any]] = []
    for candidate in attempted_keywords:
        envelope = c.fetch_hashtag_posts(keyword=candidate, feed_type=feed_type)
        posts = extract_instagram_posts(envelope)
        if posts:
            if candidate != keyword.strip().lstrip("#"):
                logger.info(
                    "Instagram hashtag search for %r matched via fallback candidate %r",
                    keyword,
                    candidate,
                )
            break

    rows = cleaned_posts_to_db_rows(posts, search_keyword=keyword, source_batch_id=source_batch_id)
    if rows:
        upsert_instagram_posts(rows)
    return envelope, posts, len(rows)
