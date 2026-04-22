from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any

import httpx

from app.core.config import get_settings
from app.db.repository import upsert_tiktok_photo_posts

logger = logging.getLogger(__name__)


FETCH_SEARCH_PHOTO_PATH = "/api/v1/tiktok/web/fetch_search_photo"
REQUEST_TIMEOUT_SECONDS = 45
MAX_RETRIES = 3


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


def extract_tiktok_photo_posts(api_response: dict[str, Any]) -> list[dict[str, Any]]:
    data_obj = normalize_tikhub_data(api_response)
    if not data_obj:
        return []

    item_list = data_obj.get("item_list")
    if not isinstance(item_list, list):
        return []

    posts: list[dict[str, Any]] = []
    for item in item_list:
        if not isinstance(item, dict):
            continue
        post_id = item.get("id")
        if post_id is None or post_id == "":
            continue

        post: dict[str, Any] = {
            "id": post_id,
            "create_time_unix": item.get("createTime"),
            "create_time": None,
            "description": (item.get("desc") or "").strip() if isinstance(item.get("desc"), str) else "",
            "author": {
                "id": (item.get("author") or {}).get("id") if isinstance(item.get("author"), dict) else None,
                "unique_id": (item.get("author") or {}).get("uniqueId")
                if isinstance(item.get("author"), dict)
                else None,
                "nickname": (item.get("author") or {}).get("nickname")
                if isinstance(item.get("author"), dict)
                else None,
                "avatar": None,
                "follower_count": (item.get("authorStats") or {}).get("followerCount")
                if isinstance(item.get("authorStats"), dict)
                else None,
                "verified": (item.get("author") or {}).get("verified", False)
                if isinstance(item.get("author"), dict)
                else False,
            },
            "image_url": None,
            "cover_url": None,
            "stats": {
                "likes": (item.get("stats") or {}).get("diggCount", 0)
                if isinstance(item.get("stats"), dict)
                else 0,
                "comments": (item.get("stats") or {}).get("commentCount", 0)
                if isinstance(item.get("stats"), dict)
                else 0,
                "shares": (item.get("stats") or {}).get("shareCount", 0)
                if isinstance(item.get("stats"), dict)
                else 0,
                "plays": (item.get("stats") or {}).get("playCount", 0)
                if isinstance(item.get("stats"), dict)
                else 0,
                "collects": (item.get("stats") or {}).get("collectCount", 0)
                if isinstance(item.get("stats"), dict)
                else 0,
            },
            "hashtags": [],
            "music": None,
            "is_ad": bool(item.get("isAd", False)),
            "share_url": f"https://www.tiktok.com/photo/{post_id}" if post_id else None,
        }

        author = item.get("author")
        if isinstance(author, dict):
            post["author"]["avatar"] = author.get("avatarLarger") or author.get("avatarMedium")

        challenges = item.get("challenges")
        if isinstance(challenges, list):
            post["hashtags"] = [ch.get("title") for ch in challenges if isinstance(ch, dict) and ch.get("title")]

        image_post = item.get("imagePost")
        if isinstance(image_post, dict):
            images = image_post.get("images")
            if isinstance(images, list) and images:
                first = images[0]
                if isinstance(first, dict):
                    image_url_obj = first.get("imageURL")
                    if isinstance(image_url_obj, dict):
                        url_list = image_url_obj.get("urlList")
                        if isinstance(url_list, list) and url_list and isinstance(url_list[0], str):
                            post["image_url"] = url_list[0]

        video = item.get("video")
        if not post["image_url"] and isinstance(video, dict):
            post["image_url"] = video.get("originCover") or video.get("cover")
            post["cover_url"] = video.get("cover")

        music = item.get("music")
        if isinstance(music, dict):
            post["music"] = {
                "title": music.get("title"),
                "author": music.get("authorName"),
                "play_url": music.get("playUrl"),
                "duration": music.get("duration"),
            }

        create_time = item.get("createTime")
        if create_time is not None:
            try:
                ts = int(create_time)
                dt = datetime.fromtimestamp(ts)
                post["create_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (OSError, ValueError, TypeError):
                pass

        posts.append(post)

    return posts


def pagination_hints(_api_response: dict[str, Any], data_obj: dict[str, Any] | None) -> dict[str, Any]:
    if not data_obj:
        return {}
    hints: dict[str, Any] = {}
    extra = data_obj.get("extra")
    if isinstance(extra, dict) and extra.get("logid"):
        hints["search_id"] = extra.get("logid")
    log_pb = data_obj.get("log_pb")
    if isinstance(log_pb, dict) and log_pb.get("impr_id"):
        hints.setdefault("search_id", log_pb.get("impr_id"))
    for key in ("cursor", "offset", "has_more", "hasMore"):
        if key in data_obj and data_obj[key] is not None:
            hints[key] = data_obj[key]
    return hints


def cleaned_posts_to_db_rows(
    posts: list[dict[str, Any]],
    *,
    search_keyword: str,
    source_batch_id: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for post in posts:
        pid = post.get("id")
        if pid is None or pid == "":
            continue
        create_unix = post.get("create_time_unix")
        try:
            create_time_unix = int(create_unix) if create_unix is not None else None
        except (TypeError, ValueError):
            create_time_unix = None

        music = post.get("music")
        rows.append(
            {
                "id": str(pid),
                "search_keyword": search_keyword,
                "create_time_unix": create_time_unix,
                "create_time": post.get("create_time"),
                "description": post.get("description") or "",
                "author_json": json.dumps(post.get("author") or {}),
                "image_url": post.get("image_url"),
                "cover_url": post.get("cover_url"),
                "stats_json": json.dumps(post.get("stats") or {}),
                "hashtags_json": json.dumps(post.get("hashtags") or []),
                "music_json": json.dumps(music) if music is not None else None,
                "is_ad": 1 if post.get("is_ad") else 0,
                "share_url": post.get("share_url"),
                "source_batch_id": source_batch_id,
            }
        )
    return rows


class TikTokPhotoClient:
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
                "TikHub TikTok photo request retry %s/%s for %s",
                attempt,
                MAX_RETRIES,
                context,
            )
            time.sleep(min(attempt, 3))

        if last_exception is not None:
            raise last_exception
        return {}

    def fetch_search_photo(
        self,
        *,
        keyword: str,
        count: int = 20,
        offset: int = 0,
        search_id: str | None = None,
        cookie: str | None = None,
    ) -> dict[str, Any]:
        if not self.settings.tikhub_api_key:
            raise RuntimeError("TIKHUB_API_KEY is not configured")

        headers = {"Authorization": f"Bearer {self.settings.tikhub_api_key}"}
        normalized_keyword = keyword.strip()
        effective_cookie = cookie if cookie not in (None, "") else self.settings.tikhub_cookie
        params: dict[str, Any] = {
            "keyword": normalized_keyword,
            "count": count,
            "offset": offset if offset > 0 else None,
            "search_id": search_id,
            "cookie": effective_cookie,
        }

        with httpx.Client(
            base_url="https://api.tikhub.io",
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as client:
            return self._request_json(
                client,
                FETCH_SEARCH_PHOTO_PATH,
                params=params,
                context=f"fetch_search_photo keyword={normalized_keyword!r}",
            )


def run_tiktok_photo_fetch_clean_save(
    *,
    keyword: str,
    count: int = 20,
    offset: int = 0,
    search_id: str | None = None,
    cookie: str | None = None,
    client: TikTokPhotoClient | None = None,
    source_batch_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    """
    Fetch from TikHub, extract posts, upsert into tiktok_photo_posts.
    Returns (envelope, posts, saved_count).
    """
    c = client or TikTokPhotoClient()
    envelope = c.fetch_search_photo(
        keyword=keyword,
        count=count,
        offset=offset,
        search_id=search_id,
        cookie=cookie,
    )
    posts = extract_tiktok_photo_posts(envelope)
    rows = cleaned_posts_to_db_rows(posts, search_keyword=keyword, source_batch_id=source_batch_id)
    if rows:
        upsert_tiktok_photo_posts(rows)
    return envelope, posts, len(rows)
