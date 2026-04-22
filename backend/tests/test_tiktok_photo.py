from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.connection import connection_scope
from app.main import app
from app.services.ingestion.ingestion_service import IngestionService
from app.services.ingestion.tiktok_photo_client import (
    TikTokPhotoClient,
    cleaned_posts_to_db_rows,
    extract_tiktok_photo_posts,
    normalize_tikhub_data,
    pagination_hints,
    run_tiktok_photo_fetch_clean_save,
)


def _minimal_item_list_item() -> dict[str, Any]:
    return {
        "id": "photo_test_1",
        "createTime": 1700000000,
        "desc": "  hello world  ",
        "author": {
            "id": "a1",
            "uniqueId": "user_one",
            "nickname": "Nick",
            "avatarLarger": "https://example.com/a.jpg",
            "verified": True,
        },
        "authorStats": {"followerCount": 100},
        "stats": {
            "diggCount": 10,
            "commentCount": 2,
            "shareCount": 1,
            "playCount": 100,
            "collectCount": 3,
        },
        "challenges": [{"title": "skincare"}, {"title": None}],
        "imagePost": {
            "images": [
                {
                    "imageURL": {
                        "urlList": ["https://example.com/img1.jpg"],
                    }
                }
            ]
        },
        "music": {
            "title": "Track",
            "authorName": "Artist",
            "playUrl": "https://example.com/m.mp3",
            "duration": 30,
        },
        "isAd": False,
    }


def _minimal_item_list_item_with_id(post_id: str) -> dict[str, Any]:
    item = _minimal_item_list_item()
    item["id"] = post_id
    return item


def test_normalize_tikhub_data_dict() -> None:
    inner = {"item_list": []}
    assert normalize_tikhub_data({"data": inner}) == inner


def test_normalize_tikhub_data_json_string() -> None:
    inner = {"item_list": [], "extra": {"logid": "abc"}}
    import json

    payload = {"data": json.dumps(inner)}
    assert normalize_tikhub_data(payload) == inner


def test_normalize_tikhub_data_invalid_json() -> None:
    assert normalize_tikhub_data({"data": "not-json{{"}) is None


def test_extract_tiktok_photo_posts_image_and_music() -> None:
    envelope = {"data": {"item_list": [_minimal_item_list_item()]}}
    posts = extract_tiktok_photo_posts(envelope)
    assert len(posts) == 1
    p = posts[0]
    assert p["id"] == "photo_test_1"
    assert p["description"] == "hello world"
    assert p["image_url"] == "https://example.com/img1.jpg"
    assert p["stats"]["likes"] == 10
    assert p["hashtags"] == ["skincare"]
    assert p["music"]["title"] == "Track"
    assert p["share_url"] == "https://www.tiktok.com/photo/photo_test_1"
    assert p["create_time"] is not None


def test_extract_video_fallback_cover() -> None:
    item = {
        "id": "v1",
        "createTime": 1700000000,
        "desc": "",
        "author": {},
        "authorStats": {},
        "stats": {},
        "challenges": [],
        "video": {"originCover": "https://oc.jpg", "cover": "https://c.jpg"},
    }
    posts = extract_tiktok_photo_posts({"data": {"item_list": [item]}})
    assert posts[0]["image_url"] == "https://oc.jpg"
    assert posts[0]["cover_url"] == "https://c.jpg"


def test_cleaned_posts_to_db_rows() -> None:
    posts = extract_tiktok_photo_posts({"data": {"item_list": [_minimal_item_list_item()]}})
    rows = cleaned_posts_to_db_rows(posts, search_keyword="niacinamide")
    assert len(rows) == 1
    assert rows[0]["id"] == "photo_test_1"
    assert rows[0]["search_keyword"] == "niacinamide"
    assert rows[0]["is_ad"] == 0
    assert "author_json" in rows[0]


def test_fetch_search_photo_uses_settings_cookie_and_omits_zero_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    settings.tikhub_api_key = "fake-token"
    settings.tikhub_cookie = "sessionid=abc123"

    captured: dict[str, Any] = {}

    def fake_request_json(
        self: TikTokPhotoClient,
        client: Any,
        path: str,
        *,
        params: dict[str, Any],
        context: str,
    ) -> dict[str, Any]:
        captured["path"] = path
        captured["params"] = params
        captured["context"] = context
        return {"data": {"item_list": []}}

    monkeypatch.setattr(TikTokPhotoClient, "_request_json", fake_request_json)

    client = TikTokPhotoClient()
    client.settings = settings
    client.fetch_search_photo(keyword="  snail mucin  ", count=5, offset=0)

    assert captured["path"] == "/api/v1/tiktok/web/fetch_search_photo"
    assert captured["params"]["keyword"] == "snail mucin"
    assert captured["params"]["offset"] is None
    assert captured["params"]["cookie"] == "sessionid=abc123"
    assert captured["context"] == "fetch_search_photo keyword='snail mucin'"


def test_pagination_hints_search_id() -> None:
    data = {"extra": {"logid": "L1"}, "log_pb": {"impr_id": "I1"}}
    hints = pagination_hints({}, data)
    assert hints["search_id"] == "L1"


@pytest.mark.usefixtures("test_database")
def test_search_route_503_without_api_key() -> None:
    with TestClient(app) as client:
        r = client.get("/tiktok/photos/search", params={"keyword": "test"})
    assert r.status_code == 503


@pytest.mark.usefixtures("test_database")
def test_search_route_persists_and_returns_posts(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    settings.tikhub_api_key = "fake-token"

    def fake_fetch(
        self: TikTokPhotoClient,
        *,
        keyword: str,
        count: int = 20,
        offset: int = 0,
        search_id: str | None = None,
        cookie: str | None = None,
    ) -> dict[str, Any]:
        return {
            "code": 200,
            "message": "ok",
            "data": {
                "item_list": [_minimal_item_list_item()],
                "extra": {"logid": "sid-123"},
            },
        }

    monkeypatch.setattr(TikTokPhotoClient, "fetch_search_photo", fake_fetch)

    with TestClient(app) as client:
        r = client.get("/tiktok/photos/search", params={"keyword": "niacinamide", "count": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["saved_count"] == 1
    assert len(body["posts"]) == 1
    assert body["posts"][0]["id"] == "photo_test_1"
    assert body["pagination"].get("search_id") == "sid-123"

    with connection_scope() as conn:
        row = conn.execute(
            "SELECT id, search_keyword FROM tiktok_photo_posts WHERE id = ?",
            ("photo_test_1",),
        ).fetchone()
    assert row is not None
    assert dict(row)["search_keyword"] == "niacinamide"


@pytest.mark.usefixtures("test_database")
def test_search_raw_route_returns_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    settings.tikhub_api_key = "fake-token"

    envelope = {"code": 200, "data": {"item_list": [_minimal_item_list_item()]}}

    def fake_fetch(self: TikTokPhotoClient, **kwargs: Any) -> dict[str, Any]:
        return envelope

    monkeypatch.setattr(TikTokPhotoClient, "fetch_search_photo", fake_fetch)

    with TestClient(app) as client:
        r = client.get("/tiktok/photos/search/raw", params={"keyword": "k"})
    assert r.status_code == 200
    body = r.json()
    assert body["saved_count"] == 1
    assert body["tikhub"]["code"] == 200


def test_run_tiktok_photo_fetch_clean_save_uses_real_pipeline(test_database, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    settings.tikhub_api_key = "fake-token"

    def fake_fetch(self: TikTokPhotoClient, **kwargs: Any) -> dict[str, Any]:
        return {"data": {"item_list": [_minimal_item_list_item()]}}

    monkeypatch.setattr(TikTokPhotoClient, "fetch_search_photo", fake_fetch)

    env, posts, n = run_tiktok_photo_fetch_clean_save(keyword="kw", client=TikTokPhotoClient())
    assert n == 1
    assert len(posts) == 1
    assert "data" in env

    with connection_scope() as conn:
        c = conn.execute("SELECT COUNT(*) AS c FROM tiktok_photo_posts").fetchone()
    assert dict(c)["c"] == 1


def test_run_tiktok_photo_fetch_clean_save_caps_saved_posts_per_keyword(test_database, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    settings.tikhub_api_key = "fake-token"

    def fake_fetch(self: TikTokPhotoClient, **kwargs: Any) -> dict[str, Any]:
        return {"data": {"item_list": [_minimal_item_list_item_with_id(f"tt-{index}") for index in range(7)]}}

    monkeypatch.setattr(TikTokPhotoClient, "fetch_search_photo", fake_fetch)

    env, posts, n = run_tiktok_photo_fetch_clean_save(keyword="kw", count=20, client=TikTokPhotoClient())
    assert n == 5
    assert len(posts) == 5
    assert "data" in env

    with connection_scope() as conn:
        c = conn.execute("SELECT COUNT(*) AS c FROM tiktok_photo_posts").fetchone()
    assert dict(c)["c"] == 5


@pytest.mark.usefixtures("test_database")
def test_ingestion_run_with_tiktok_source(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.schemas import IngestionRunRequest

    settings = get_settings()
    settings.tikhub_api_key = "fake-token"

    def fake_fetch(self: TikTokPhotoClient, **kwargs: Any) -> dict[str, Any]:
        return {"data": {"item_list": [_minimal_item_list_item()]}}

    monkeypatch.setattr(TikTokPhotoClient, "fetch_search_photo", fake_fetch)

    request = IngestionRunRequest(
        market="HK",
        category="skincare",
        recent_days=7,
        sources=["tiktok"],
        target_keywords=["alpha"],
        suggested_keywords=["alpha"],
        max_target_keywords=5,
    )
    svc = IngestionService()
    svc.settings = settings
    svc.tiktok_photo_client.settings = settings
    run_id, batch_id = svc.create_run(request)
    svc.run(run_id, batch_id, request)

    with connection_scope() as conn:
        row = conn.execute(
            "SELECT source_batch_id FROM tiktok_photo_posts WHERE id = ?",
            ("photo_test_1",),
        ).fetchone()
    assert row is not None
    assert dict(row)["source_batch_id"] == batch_id
