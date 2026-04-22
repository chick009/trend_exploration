from __future__ import annotations

import httpx

from app.db.repository import fetch_posts_for_scoring, upsert_instagram_posts, upsert_tiktok_photo_posts
from app.services.ingestion.rednote_client import RednoteClient


def test_rednote_synthetic_posts_respect_limits(test_database) -> None:
    client = RednoteClient()

    rows = client.fetch_posts(
        market="HK",
        category="skincare",
        recent_days=7,
        seed_terms=["niacinamide", "ceramide"],
        max_notes_per_keyword=2,
        max_comment_posts_per_keyword=1,
        max_comments_per_post=3,
    )

    assert len(rows) == 4


def test_rednote_app_v2_calls_respect_comment_limits(test_database, monkeypatch) -> None:
    requests: list[tuple[str, dict]] = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, path: str, params: dict) -> FakeResponse:
            requests.append((path, params))
            if path.endswith("/search_notes"):
                return FakeResponse(
                    {
                        "data": {
                            "items": [
                                {
                                    "note_id": "note-1",
                                    "title": "Niacinamide note",
                                    "desc": "Brightening routine",
                                    "tags": ["niacinamide"],
                                    "share_text": "http://xhslink.com/note-1",
                                    "interact_info": {
                                        "liked_count": 1200,
                                        "collected_count": 80,
                                        "comment_count": 10,
                                        "share_count": 4,
                                    },
                                },
                                {
                                    "note_id": "note-2",
                                    "title": "Ceramide note",
                                    "desc": "Barrier repair",
                                    "tags": ["ceramide"],
                                    "share_text": "http://xhslink.com/note-2",
                                    "interact_info": {
                                        "liked_count": 800,
                                        "collected_count": 60,
                                        "comment_count": 6,
                                        "share_count": 2,
                                    },
                                },
                                {
                                    "note_id": "note-3",
                                    "title": "Extra note",
                                    "desc": "Should be trimmed by max_notes_per_keyword",
                                    "tags": [],
                                    "share_text": "http://xhslink.com/note-3",
                                    "interact_info": {
                                        "liked_count": 500,
                                        "collected_count": 10,
                                        "comment_count": 1,
                                        "share_count": 0,
                                    },
                                },
                            ]
                        }
                    }
                )
            if path.endswith("/get_note_comments"):
                return FakeResponse(
                    {
                        "data": {
                            "comments": [
                                {"content": "Love this niacinamide serum"},
                                {"content": "Helps with dark spots"},
                                {"content": "Should be trimmed by max_comments_per_post"},
                            ]
                        }
                    }
                )
            raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(httpx, "Client", FakeClient)

    client = RednoteClient()
    client.settings.tikhub_api_key = "test-token"
    client.entity_dictionary = {}

    rows = client.fetch_posts(
        market="HK",
        category="skincare",
        recent_days=7,
        seed_terms=["niacinamide"],
        max_notes_per_keyword=2,
        max_comment_posts_per_keyword=1,
        max_comments_per_post=2,
    )

    assert len(rows) == 2
    assert requests[0][0] == "/api/v1/xiaohongshu/app_v2/search_notes"
    assert requests[0][1]["keyword"] == "niacinamide"
    assert requests[1][0] == "/api/v1/xiaohongshu/app_v2/get_note_comments"
    assert requests[1][1]["note_id"] == "note-1"
    assert requests[1][1]["share_text"] == "http://xhslink.com/note-1"
    assert rows[0]["source_payload"]["comments_preview"] == [
        "Love this niacinamide serum",
        "Helps with dark spots",
    ]
    assert rows[1]["source_payload"]["comments_preview"] == []


def test_rednote_search_falls_back_to_web_on_app_v2_400(test_database, monkeypatch) -> None:
    requests: list[tuple[str, dict]] = []

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict | None = None) -> None:
            self.status_code = status_code
            self._payload = payload or {}

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                request = httpx.Request("GET", "https://api.tikhub.io/test")
                raise httpx.HTTPStatusError("err", request=request, response=self)

        def json(self) -> dict:
            return self._payload

        @property
        def text(self) -> str:
            return '{"detail":"bad"}'

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, path: str, params: dict) -> FakeResponse:
            requests.append((path, params))
            if path.endswith("/app_v2/search_notes"):
                return FakeResponse(400)
            if path.endswith("/web/search_notes"):
                return FakeResponse(
                    200,
                    {
                        "data": {
                            "items": [
                                {
                                    "note_id": "web-1",
                                    "title": "From web",
                                    "desc": "Body",
                                    "tags": ["x"],
                                    "interact_info": {"liked_count": 10, "collected_count": 1, "comment_count": 0, "share_count": 0},
                                }
                            ]
                        }
                    },
                )
            raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(httpx, "Client", FakeClient)

    client = RednoteClient()
    client.settings.tikhub_api_key = "test-token"
    client.entity_dictionary = {}

    rows = client.fetch_posts(
        market="HK",
        category="skincare",
        recent_days=7,
        seed_terms=["alpha"],
        max_notes_per_keyword=5,
        max_comment_posts_per_keyword=0,
        max_comments_per_post=3,
    )

    assert len(rows) == 1
    assert requests[0][0].endswith("/app_v2/search_notes")
    assert requests[1][0].endswith("/web/search_notes")
    assert rows[0]["id"] == "web-1"


def test_fetch_posts_for_scoring_caps_rows_per_keyword_and_source(test_database) -> None:
    batch_id = "batch-cap-test"
    upsert_instagram_posts(
        [
            {
                "post_id": f"ig-{index}",
                "search_keyword": "collagen",
                "code": f"ig-code-{index}",
                "username": "creator",
                "full_name": "Creator",
                "caption": f"Instagram post {index}",
                "hashtags_json": "[]",
                "mentions_json": "[]",
                "likes": 10 + index,
                "comments": 1,
                "views": 20,
                "is_video": 0,
                "created_at": f"2026-04-0{(index % 7) + 1}T10:00:00",
                "location_name": None,
                "city": None,
                "lat": None,
                "lng": None,
                "source_batch_id": batch_id,
            }
            for index in range(7)
        ]
    )
    upsert_tiktok_photo_posts(
        [
            {
                "id": f"tt-{index}",
                "search_keyword": "collagen",
                "create_time_unix": 1712000000 + index,
                "create_time": f"2026-04-0{(index % 7) + 1} 10:00:00",
                "description": f"TikTok post {index}",
                "author_json": "{}",
                "image_url": None,
                "cover_url": None,
                "stats_json": "{}",
                "hashtags_json": "[]",
                "music_json": None,
                "is_ad": 0,
                "share_url": None,
                "source_batch_id": batch_id,
            }
            for index in range(7)
        ]
    )

    rows = fetch_posts_for_scoring(batch_id)

    instagram_rows = [row for row in rows if row["source_table"] == "instagram_posts"]
    tiktok_rows = [row for row in rows if row["source_table"] == "tiktok_photo_posts"]
    assert len(instagram_rows) == 5
    assert len(tiktok_rows) == 5
