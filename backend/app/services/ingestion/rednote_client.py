from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.core.config import get_settings
from app.db.repository import get_entity_dictionary

logger = logging.getLogger(__name__)


def compute_engagement_score(
    liked_count: int,
    collected_count: int,
    comment_count: int,
    share_count: int,
) -> float:
    weighted = liked_count + collected_count * 2 + comment_count * 3 + share_count * 4
    return min(weighted / 10000, 1.0)


class RednoteClient:
    SEARCH_NOTES_PATH = "/api/v1/xiaohongshu/app_v2/search_notes"
    SEARCH_NOTES_WEB_PATH = "/api/v1/xiaohongshu/web/search_notes"
    NOTE_COMMENTS_PATH = "/api/v1/xiaohongshu/app_v2/get_note_comments"
    NOTE_COMMENTS_WEB_PATH = "/api/v1/xiaohongshu/web/get_note_comments"
    REQUEST_TIMEOUT_SECONDS = 45
    MAX_RETRIES = 3

    def __init__(self) -> None:
        self.settings = get_settings()
        self.entity_dictionary: dict[str, dict] | None = None

    def fetch_posts(
        self,
        *,
        market: str,
        category: str,
        recent_days: int,
        seed_terms: list[str],
        max_notes_per_keyword: int,
        max_comment_posts_per_keyword: int,
        max_comments_per_post: int,
    ) -> list[dict]:
        if not self.settings.tikhub_api_key:
            return self._synthetic_posts(
                market=market,
                category=category,
                recent_days=recent_days,
                seed_terms=seed_terms,
                max_notes_per_keyword=max_notes_per_keyword,
            )

        headers = {"Authorization": f"Bearer {self.settings.tikhub_api_key}"}
        rows: list[dict] = []
        with httpx.Client(
            base_url="https://api.tikhub.io",
            headers=headers,
            timeout=self.REQUEST_TIMEOUT_SECONDS,
        ) as client:
            for term in seed_terms:
                try:
                    payload = self._search_notes_payload(client, term)
                except httpx.HTTPError as exc:
                    logger.warning("TikHub note search failed for term '%s': %s", term, exc)
                    continue

                notes = self._normalize_collection(payload.get("data", []))
                comment_fetches = 0
                for item in notes[:max_notes_per_keyword]:
                    note_id_value = item.get("note_id") or item.get("id")
                    if note_id_value in (None, ""):
                        continue
                    note_id = str(note_id_value)

                    interact_info = item.get("interact_info", {}) if isinstance(item.get("interact_info"), dict) else {}
                    liked_count = self._extract_metric(item, interact_info, "liked_count", "like_count")
                    collected_count = self._extract_metric(item, interact_info, "collected_count", "collect_count")
                    comment_count = self._extract_metric(item, interact_info, "comment_count")
                    share_count = self._extract_metric(item, interact_info, "share_count")
                    should_fetch_comments = comment_fetches < max_comment_posts_per_keyword
                    comment_texts: list[str] = []
                    if should_fetch_comments:
                        try:
                            comment_texts = self._fetch_note_comments(
                                client,
                                note_id=note_id,
                                share_text=self._extract_share_text(item),
                                max_comments_per_post=max_comments_per_post,
                            )
                        except httpx.HTTPError as exc:
                            logger.warning("TikHub comment fetch failed for note '%s': %s", note_id, exc)
                    if should_fetch_comments:
                        comment_fetches += 1
                    comment_mentions = self._extract_mentions(" ".join(comment_texts))
                    created_at = item.get("create_time")
                    rows.append(
                        {
                            "id": note_id,
                            "region": self._extract_region(item, market),
                            "post_date": self._normalize_post_date(created_at),
                            "title": item.get("title", term.title()),
                            "content_text": item.get("desc", ""),
                            "hashtags": item.get("tags", []),
                            "entity_mentions": [],
                            "comment_mentions": comment_mentions,
                            "liked_count": liked_count,
                            "collected_count": collected_count,
                            "comment_count": comment_count,
                            "share_count": share_count,
                            "engagement_score": compute_engagement_score(
                                liked_count, collected_count, comment_count, share_count
                            ),
                            "seed_keyword": term,
                            "source_payload": {
                                "note": item,
                                "comments_preview": comment_texts,
                            },
                        }
                    )
        return rows

    def _fetch_note_comments(
        self,
        client: httpx.Client,
        *,
        note_id: str,
        share_text: str,
        max_comments_per_post: int,
    ) -> list[str]:
        payload: dict[str, Any]
        if share_text.strip():
            try:
                payload = self._request_json(
                    client,
                    self.NOTE_COMMENTS_PATH,
                    params=self._build_comment_params(note_id, share_text),
                    context=f"app_v2:get_note_comments:{note_id}",
                )
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:400] if exc.response is not None else ""
                logger.warning(
                    "TikHub app_v2 get_note_comments HTTP %s for note '%s'; using web endpoint. %s",
                    exc.response.status_code if exc.response else "?",
                    note_id,
                    detail,
                )
                payload = self._request_json(
                    client,
                    self.NOTE_COMMENTS_WEB_PATH,
                    params={"note_id": note_id, "lastCursor": ""},
                    context=f"web:get_note_comments:{note_id}",
                )
        else:
            payload = self._request_json(
                client,
                self.NOTE_COMMENTS_WEB_PATH,
                params={"note_id": note_id, "lastCursor": ""},
                context=f"web:get_note_comments:{note_id}",
            )
        comments = self._normalize_collection(payload.get("data", []), preferred_keys=("comments", "items", "data"))
        snippets: list[str] = []
        for comment in comments[:max_comments_per_post]:
            content = comment.get("content") or comment.get("text") or ""
            if content:
                snippets.append(content)
        return snippets

    def _search_notes_payload(self, client: httpx.Client, term: str) -> dict[str, Any]:
        """Prefer app_v2 (matches TikHub docs); fall back to web if app_v2 rejects the request."""
        cleaned = " ".join(term.split())
        app_params = self._build_app_v2_search_params(cleaned)
        try:
            return self._request_json(
                client,
                self.SEARCH_NOTES_PATH,
                params=app_params,
                context=f"app_v2:search_notes:{cleaned}",
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:400] if exc.response is not None else ""
            logger.warning(
                "TikHub app_v2 search_notes HTTP %s for '%s'; falling back to web. %s",
                exc.response.status_code if exc.response else "?",
                cleaned,
                detail,
            )
            web_params = {"keyword": cleaned, "page": 1, "sort_type": "hot", "note_type": 0}
            return self._request_json(
                client,
                self.SEARCH_NOTES_WEB_PATH,
                params=web_params,
                context=f"web:search_notes:{cleaned}",
            )

    def _build_app_v2_search_params(self, keyword: str) -> dict[str, Any]:
        """First-page search: omit empty search_id / search_session_id (TikHub rejects many empty-string params)."""
        return {
            "keyword": keyword,
            "page": 1,
            "sort_type": "general",
            "note_type": "不限",
            "time_filter": "不限",
            "source": "explore_feed",
            "ai_mode": 0,
        }

    def _build_comment_params(self, note_id: str, share_text: str) -> dict[str, Any]:
        return {
            "note_id": note_id,
            "share_text": share_text,
            "cursor": "",
            "index": 0,
            "pageArea": "UNFOLDED",
            "sort_strategy": "latest_v2",
        }

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

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = client.get(path, params=params)
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, dict) else {}
            except httpx.HTTPStatusError as exc:
                last_exception = exc
                status_code = exc.response.status_code
                if status_code < 500 or attempt == self.MAX_RETRIES:
                    raise
            except httpx.RequestError as exc:
                last_exception = exc
                if attempt == self.MAX_RETRIES:
                    raise

            logger.warning(
                "TikHub request retry %s/%s for %s",
                attempt,
                self.MAX_RETRIES,
                context,
            )
            time.sleep(min(attempt, 3))

        if last_exception is not None:
            raise last_exception
        return {}

    @staticmethod
    def _drop_empty_params(params: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in params.items() if value is not None and value != ""}

    def _normalize_collection(
        self,
        value: object,
        *,
        preferred_keys: tuple[str, ...] = ("items", "notes", "data", "list"),
    ) -> list[dict]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            for key in preferred_keys:
                nested = value.get(key)
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
                if isinstance(nested, dict):
                    normalized = self._normalize_collection(nested, preferred_keys=preferred_keys)
                    if normalized:
                        return normalized
            return [item for item in value.values() if isinstance(item, dict)]
        return []

    def _extract_mentions(self, text: str) -> list[str]:
        if not text:
            return []
        if self.entity_dictionary is None:
            self.entity_dictionary = get_entity_dictionary()
        normalized = text.lower()
        matches: list[str] = []
        for canonical, metadata in self.entity_dictionary.items():
            aliases = [canonical, *metadata["aliases"]]
            if any(alias.lower() in normalized for alias in aliases):
                matches.append(canonical)
        return sorted(set(matches))

    def _extract_share_text(self, item: dict[str, Any]) -> str:
        for value in (
            item.get("share_text"),
            item.get("share_link"),
            item.get("share_url"),
        ):
            if isinstance(value, str) and value:
                return value

        share_info = item.get("share_info")
        if isinstance(share_info, dict):
            for key in ("share_text", "share_link", "share_url", "link", "url"):
                value = share_info.get(key)
                if isinstance(value, str) and value:
                    return value
        return ""

    def _extract_metric(self, item: dict[str, Any], interact_info: dict[str, Any], *keys: str) -> int:
        for key in keys:
            value = interact_info.get(key)
            parsed = self._to_int(value)
            if parsed is not None:
                return parsed

            value = item.get(key)
            parsed = self._to_int(value)
            if parsed is not None:
                return parsed
        return 0

    def _to_int(self, value: object) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _extract_region(self, item: dict, market: str) -> str:
        location = (
            item.get("user", {}).get("location")
            or item.get("user", {}).get("ip_location")
            or item.get("ip_location")
            or ""
        )
        normalized = str(location).upper()
        for region in ("HK", "KR", "TW", "SG"):
            if region in normalized:
                return region
        return market if market != "cross" else "HK"

    def _normalize_post_date(self, raw_value: object) -> str:
        if isinstance(raw_value, (int, float)):
            timestamp = int(raw_value)
            if timestamp > 10_000_000_000:
                timestamp = int(timestamp / 1000)
            return datetime.utcfromtimestamp(timestamp).date().isoformat()
        if isinstance(raw_value, str) and raw_value:
            try:
                return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).date().isoformat()
            except ValueError:
                return raw_value[:10]
        return datetime.utcnow().date().isoformat()

    def _synthetic_posts(
        self,
        *,
        market: str,
        category: str,
        recent_days: int,
        seed_terms: list[str],
        max_notes_per_keyword: int,
    ) -> list[dict]:
        rows: list[dict] = []
        base_region = market if market != "cross" else "HK"
        for term in seed_terms:
            randomizer = random.Random(f"rednote:{market}:{category}:{term}:{recent_days}")
            for index in range(max_notes_per_keyword):
                liked_count = randomizer.randint(300, 2200)
                collected_count = randomizer.randint(80, 700)
                comment_count = randomizer.randint(20, 220)
                share_count = randomizer.randint(10, 180)
                if base_region == "HK" and term in {"tranexamic acid", "glass skin"}:
                    liked_count += 600
                    collected_count += 200
                if base_region == "KR" and term in {"bakuchiol", "cica"}:
                    liked_count += 400
                created_at = datetime.utcnow() - timedelta(days=randomizer.randint(0, max(recent_days - 1, 0)))
                rows.append(
                    {
                        "id": f"{base_region}-{term.replace(' ', '-')}-{index}",
                        "region": base_region,
                        "post_date": created_at.date().isoformat(),
                        "title": f"{term.title()} routine everyone is saving",
                        "content_text": (
                            f"Loving this {term} discovery for {category}. "
                            "The texture is gentle, glowy, and people keep asking for the routine."
                        ),
                        "hashtags": [term.replace(" ", ""), category, "viralbeauty"],
                        "entity_mentions": [term],
                        "comment_mentions": [f"{term} works so well", f"anyone tried this {term} product?"],
                        "liked_count": liked_count,
                        "collected_count": collected_count,
                        "comment_count": comment_count,
                        "share_count": share_count,
                        "engagement_score": compute_engagement_score(
                            liked_count, collected_count, comment_count, share_count
                        ),
                        "seed_keyword": term,
                        "source_payload": {
                            "synthetic": True,
                            "market": base_region,
                            "comments_preview": [f"{term} works so well", f"anyone tried this {term} product?"],
                        },
                    }
                )
        return rows
