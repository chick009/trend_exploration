from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.connection import connection_scope
from app.main import app
from app.services.ingestion.ingestion_service import IngestionService
from app.services.ingestion.instagram_client import (
    InstagramClient,
    build_hashtag_keyword_candidates,
    cleaned_posts_to_db_rows,
    extract_instagram_posts,
    normalize_tikhub_data,
    pagination_hints,
    run_instagram_fetch_clean_save,
)


def _minimal_item() -> dict[str, Any]:
    return {
        "id": "3878984374997842506",
        "code": "DXU67zBCXpK",
        "caption_text": "Example caption",
        "caption_hashtags": ["#skincare", "#fyp"],
        "caption_mentions": ["@brand", "@creator"],
        "like_count": 1217,
        "comment_count": 6,
        "play_count": 118902,
        "is_video": True,
        "taken_at": "2026-04-19T20:40:27Z",
        "user": {
            "username": "vaaaaalo",
            "full_name": "Valo",
            "is_verified": True,
        },
        "location": {
            "name": "Los Angeles, California",
            "city": "",
            "lat": 34.053556804931,
            "lng": -118.26243695301,
        },
    }


def _minimal_item_with_id(post_id: str) -> dict[str, Any]:
    item = _minimal_item()
    item["id"] = post_id
    item["code"] = f"code-{post_id}"
    return item


def test_normalize_tikhub_data_dict() -> None:
    inner = {"data": {"items": []}}
    assert normalize_tikhub_data({"data": inner}) == inner


def test_extract_instagram_posts_happy_path() -> None:
    envelope = {"data": {"data": {"items": [_minimal_item()]}}}
    posts = extract_instagram_posts(envelope)
    assert len(posts) == 1
    post = posts[0]
    assert post["post_id"] == "3878984374997842506"
    assert post["code"] == "DXU67zBCXpK"
    assert post["username"] == "vaaaaalo"
    assert post["full_name"] == "Valo"
    assert post["caption"] == "Example caption"
    assert post["hashtags"] == ["skincare", "fyp"]
    assert post["mentions"] == ["brand", "creator"]
    assert post["likes"] == 1217
    assert post["comments"] == 6
    assert post["views"] == 118902
    assert post["is_video"] is True
    assert post["created_at"] == "2026-04-19T20:40:27Z"
    assert post["location_name"] == "Los Angeles, California"


def test_extract_handles_missing_user_location() -> None:
    item = _minimal_item()
    item.pop("user")
    item["location"] = None
    posts = extract_instagram_posts({"data": {"data": {"items": [item]}}})
    assert len(posts) == 1
    post = posts[0]
    assert post["username"] is None
    assert post["full_name"] is None
    assert post["location_name"] is None
    assert post["city"] is None


def test_cleaned_posts_to_db_rows_serializes_json() -> None:
    posts = extract_instagram_posts({"data": {"data": {"items": [_minimal_item()]}}})
    rows = cleaned_posts_to_db_rows(posts, search_keyword="cat")
    assert len(rows) == 1
    row = rows[0]
    assert row["post_id"] == "3878984374997842506"
    assert row["search_keyword"] == "cat"
    assert row["hashtags_json"] == '["skincare", "fyp"]'
    assert row["mentions_json"] == '["brand", "creator"]'
    assert row["is_video"] == 1


def test_build_hashtag_keyword_candidates_normalizes_phrase() -> None:
    candidates = build_hashtag_keyword_candidates(" #COSRX snail mucin essence ")
    assert candidates == [
        "COSRX snail mucin essence",
        "cosrxsnailmucinessence",
        "cosrxsnailmucin",
        "cosrx",
    ]


def test_pagination_hints_has_more() -> None:
    hints = pagination_hints({}, {"data": {"has_more": False}})
    assert hints == {"has_more": False}


@pytest.mark.usefixtures("test_database")
def test_search_route_503_without_api_key() -> None:
    with TestClient(app) as client:
        response = client.get("/instagram/hashtag/search", params={"keyword": "cat"})
    assert response.status_code == 503


@pytest.mark.usefixtures("test_database")
def test_search_route_persists_and_returns_posts(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    settings.tikhub_api_key = "fake-token"

    def fake_fetch(
        self: InstagramClient,
        *,
        keyword: str,
        feed_type: str = "top",
    ) -> dict[str, Any]:
        assert keyword == "cat"
        assert feed_type == "top"
        return {
            "code": 200,
            "message": "ok",
            "data": {
                "data": {
                    "items": [_minimal_item()],
                    "has_more": False,
                }
            },
        }

    monkeypatch.setattr(InstagramClient, "fetch_hashtag_posts", fake_fetch)

    with TestClient(app) as client:
        response = client.get("/instagram/hashtag/search", params={"keyword": "cat"})
    assert response.status_code == 200
    body = response.json()
    assert body["saved_count"] == 1
    assert len(body["posts"]) == 1
    assert body["posts"][0]["post_id"] == "3878984374997842506"
    assert body["pagination"] == {"has_more": False}

    with connection_scope() as conn:
        row = conn.execute(
            "SELECT post_id, search_keyword FROM instagram_posts WHERE post_id = ?",
            ("3878984374997842506",),
        ).fetchone()
    assert row is not None
    assert dict(row)["search_keyword"] == "cat"


@pytest.mark.usefixtures("test_database")
def test_search_raw_route_returns_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    settings.tikhub_api_key = "fake-token"

    envelope = {"code": 200, "data": {"data": {"items": [_minimal_item()]}}}

    def fake_fetch(self: InstagramClient, **kwargs: Any) -> dict[str, Any]:
        return envelope

    monkeypatch.setattr(InstagramClient, "fetch_hashtag_posts", fake_fetch)

    with TestClient(app) as client:
        response = client.get("/instagram/hashtag/search/raw", params={"keyword": "cat"})
    assert response.status_code == 200
    body = response.json()
    assert body["saved_count"] == 1
    assert body["tikhub"]["code"] == 200


def test_run_instagram_fetch_clean_save_uses_real_pipeline(test_database, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    settings.tikhub_api_key = "fake-token"

    def fake_fetch(self: InstagramClient, **kwargs: Any) -> dict[str, Any]:
        return {"data": {"data": {"items": [_minimal_item()]}}}

    monkeypatch.setattr(InstagramClient, "fetch_hashtag_posts", fake_fetch)

    envelope, posts, saved_count = run_instagram_fetch_clean_save(keyword="cat", client=InstagramClient())
    assert saved_count == 1
    assert len(posts) == 1
    assert "data" in envelope

    with connection_scope() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM instagram_posts").fetchone()
    assert dict(count)["c"] == 1


def test_run_instagram_fetch_clean_save_caps_saved_posts_per_keyword(test_database, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    settings.tikhub_api_key = "fake-token"

    def fake_fetch(self: InstagramClient, **kwargs: Any) -> dict[str, Any]:
        items = [_minimal_item_with_id(f"ig-{index}") for index in range(7)]
        return {"data": {"data": {"items": items}}}

    monkeypatch.setattr(InstagramClient, "fetch_hashtag_posts", fake_fetch)

    envelope, posts, saved_count = run_instagram_fetch_clean_save(keyword="cat", client=InstagramClient())
    assert saved_count == 5
    assert len(posts) == 5
    assert "data" in envelope

    with connection_scope() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM instagram_posts").fetchone()
    assert dict(count)["c"] == 5


def test_run_instagram_fetch_clean_save_retries_hashtag_variants(
    test_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    settings.tikhub_api_key = "fake-token"
    attempted_keywords: list[str] = []

    def fake_fetch(self: InstagramClient, *, keyword: str, feed_type: str = "top") -> dict[str, Any]:
        attempted_keywords.append(keyword)
        if keyword == "COSRX snail mucin essence":
            return {"data": {"data": {"items": []}}}
        if keyword == "cosrxsnailmucinessence":
            return {"data": {"data": {"items": [_minimal_item()]}}}
        raise AssertionError(f"Unexpected fallback keyword: {keyword}")

    monkeypatch.setattr(InstagramClient, "fetch_hashtag_posts", fake_fetch)

    envelope, posts, saved_count = run_instagram_fetch_clean_save(
        keyword="COSRX snail mucin essence",
        feed_type="recent",
        client=InstagramClient(),
    )

    assert saved_count == 1
    assert len(posts) == 1
    assert attempted_keywords == ["COSRX snail mucin essence", "cosrxsnailmucinessence"]
    assert "data" in envelope


@pytest.mark.usefixtures("test_database")
def test_ingestion_run_with_instagram_source(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.schemas import IngestionRunRequest

    settings = get_settings()
    settings.tikhub_api_key = "fake-token"

    def fake_fetch(self: InstagramClient, **kwargs: Any) -> dict[str, Any]:
        return {"data": {"data": {"items": [_minimal_item()]}}}

    monkeypatch.setattr(InstagramClient, "fetch_hashtag_posts", fake_fetch)

    request = IngestionRunRequest(
        market="HK",
        category="skincare",
        recent_days=7,
        sources=["instagram"],
        target_keywords=["cat"],
        suggested_keywords=["cat"],
        max_target_keywords=5,
    )
    service = IngestionService()
    service.settings = settings
    service.instagram_client.settings = settings
    run_id, batch_id = service.create_run(request)
    service.run(run_id, batch_id, request)

    with connection_scope() as conn:
        row = conn.execute(
            "SELECT source_batch_id FROM instagram_posts WHERE post_id = ?",
            ("3878984374997842506",),
        ).fetchone()
    assert row is not None
    assert dict(row)["source_batch_id"] == batch_id
