from __future__ import annotations

import json
import re

import httpx
from fastapi.testclient import TestClient

from app.api.routes.ingestion import service as ingestion_service
from app.db.connection import connection_scope
from app.db.repository import upsert_instagram_posts, upsert_tiktok_photo_posts
from app.graph import llm as graph_llm
from app.main import app
from app.services.ingestion import ingestion_service as ingestion_module


def _message_text(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        parts: list[str] = []
        for item in payload:
            if isinstance(item, tuple) and len(item) == 2:
                parts.append(str(item[1]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(payload)


def _extract_terms(text: str) -> list[str]:
    matches = re.findall(r'"canonical_term"\s*:\s*"([^"]+)"', text)
    seen: list[str] = []
    for match in matches:
        if match not in seen:
            seen.append(match)
    return seen


class _JsonChatResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class WatchOnlySynthChatModel:
    def invoke(self, payload: object) -> _JsonChatResponse:
        text = _message_text(payload)
        schema_match = re.search(r"Schema name:\s*(\w+)", text)
        schema_name = schema_match.group(1) if schema_match else ""

        if schema_name == "QueryIntent":
            market_match = re.search(r"requested_market:\s*(\w+)", text)
            requested_market = market_match.group(1) if market_match else "HK"
            category_match = re.search(r"requested_category:\s*(\w+)", text)
            requested_category = category_match.group(1) if category_match else "skincare"
            recency_match = re.search(r"requested_recency_days:\s*(\d+)", text)
            requested_recency = int(recency_match.group(1)) if recency_match else 14
            mode_match = re.search(r"requested_analysis_mode:\s*(\w+)", text)
            analysis_mode = mode_match.group(1) if mode_match else "single_market"
            markets = ["HK", "KR", "TW", "SG"] if requested_market == "cross" or analysis_mode == "cross_market" else [requested_market]
            return _JsonChatResponse(
                json.dumps(
                    {
                        "markets": markets,
                        "category": requested_category,
                        "recency_days": requested_recency,
                        "entity_types": ["ingredient", "brand", "function"],
                        "analysis_mode": analysis_mode,
                        "focus_hint": None,
                    }
                )
            )

        if schema_name == "LensCandidateBatch":
            terms = _extract_terms(text)[:5] or ["niacinamide", "ceramide", "cica"]
            return _JsonChatResponse(
                json.dumps(
                    {
                        "candidates": [
                            {
                                "canonical_term": term,
                                "entity_type": "ingredient",
                                "lens": "Momentum",
                                "trend_statement": (
                                    "Consumers are shifting toward gentler barrier-supporting routines as sensitivity complaints rise."
                                ),
                                "data_pattern": f"{term} shows multiple reinforcing rows in the provided market slice.",
                                "viral_reasoning": f"{term} is appearing across more than one signal, which suggests momentum instead of isolated noise.",
                                "strongest_signal": "social",
                                "weakest_signal": "sales",
                                "self_confidence": "medium",
                            }
                            for term in terms
                        ]
                    }
                )
            )

        if schema_name == "SynthesizerVerdictBatch":
            terms = _extract_terms(text)
            return _JsonChatResponse(
                json.dumps(
                    {
                        "verdicts": [
                            {
                                "canonical_term": term,
                                "status": "watch",
                                "trend_statement": None,
                                "challenge_notes": [f"{term} still lacks enough multi-signal confirmation."],
                                "hype_only": False,
                                "seasonal_risk": False,
                            }
                            for term in terms
                        ]
                    }
                )
            )

        return _JsonChatResponse("Ok")


def test_health_preflight_allows_local_frontend_origin(test_database) -> None:
    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200, response.text
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_keyword_suggestion_endpoint_returns_keywords_and_recency_support(test_database) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/ingestion_runs/keyword_suggestions",
            json={
                "market": "HK",
                "category": "skincare",
                "recent_days": 7,
                "sources": ["google_trends", "instagram", "sales"],
                "max_target_keywords": 4,
            },
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["suggestions"]
    assert len(payload["suggestions"]) <= 4
    assert {item["source"] for item in payload["recency_support"]} == {"google_trends", "instagram", "sales"}


def test_ingestion_accepts_tiktok_in_sources(test_database) -> None:
    """Regression: IngestionRunRequest must allow tiktok (requires current app.models.schemas)."""
    with TestClient(app) as client:
        response = client.post(
            "/ingestion_runs",
            json={
                "market": "HK",
                "category": "skincare",
                "recent_days": 7,
                "sources": ["tiktok", "sales"],
                "target_keywords": ["alpha"],
                "suggested_keywords": ["alpha"],
            },
        )
    assert response.status_code == 200, response.text


def test_ingestion_rejects_rednote_source(test_database) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/ingestion_runs",
            json={
                "market": "HK",
                "category": "skincare",
                "recent_days": 7,
                "sources": ["rednote", "sales"],
                "target_keywords": ["alpha"],
            },
        )
    assert response.status_code == 422, response.text


def test_ingestion_then_analysis_flow(test_database) -> None:
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200

        ingestion_response = client.post(
            "/ingestion_runs",
            json={
                "market": "HK",
                "category": "skincare",
                "recent_days": 7,
                "sources": ["google_trends", "sales"],
                "target_keywords": ["niacinamide", "Beauty of Joseon"],
                "suggested_keywords": ["niacinamide", "Beauty of Joseon"],
            },
        )
        assert ingestion_response.status_code == 200
        ingestion_run = ingestion_response.json()
        status_response = client.get(f"/ingestion_runs/{ingestion_run['id']}")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "completed"

        analysis_response = client.post(
            "/analysis_runs",
            json={
                "market": "HK",
                "category": "skincare",
                "recency_days": 14,
                "analysis_mode": "single_market",
            },
        )
        assert analysis_response.status_code == 200
        analysis_run = analysis_response.json()

        analysis_status = client.get(f"/analysis_runs/{analysis_run['id']}")
        assert analysis_status.status_code == 200
        payload = analysis_status.json()
        assert payload["status"] == "completed"
        assert payload["report"]["market"] == "HK"
        assert "trends" in payload["report"]
        first_card = (payload["report"]["trends"] or payload["report"]["watch_list"])[0]
        assert "lifecycle_stage" in first_card
        assert "challenge_notes" in first_card
        assert {"intent_parser", "backend_preload", "trend_gen_agent", "evidence_synthesizer", "formatter", "memory_write"} <= set(
            payload["node_outputs"].keys()
        )
        llm_invocation = next(entry for entry in payload["tool_invocations"] if entry["tool_kind"] == "llm")
        assert llm_invocation["system_prompt"]
        assert llm_invocation["user_prompt"]
        assert llm_invocation["response_text"]
        assert payload["node_outputs"]["intent_parser"]["received_state"]["market"] == "HK"
        assert payload["node_outputs"]["intent_parser"]["emitted_state"]["query_intent"]["markets"] == ["HK"]
        assert payload["node_outputs"]["formatter"]["emitted_state"]["report_id"] == payload["report"]["report_id"]

        latest_response = client.get("/trends/latest", params={"market": "HK", "category": "skincare"})
        assert latest_response.status_code == 200


def test_google_trends_timeout_becomes_guardrail_not_failed_run(test_database, monkeypatch) -> None:
    def fake_fetch_trends(*, market: str, category: str, recent_days: int, seed_terms: list[str]):
        raise httpx.ReadTimeout("The read operation timed out")

    monkeypatch.setattr(ingestion_service.serpapi_client, "fetch_trends", fake_fetch_trends)

    with TestClient(app) as client:
        response = client.post(
            "/ingestion_runs",
            json={
                "market": "HK",
                "category": "skincare",
                "recent_days": 7,
                "sources": ["google_trends", "sales"],
                "target_keywords": ["niacinamide"],
                "suggested_keywords": ["niacinamide"],
            },
        )
        assert response.status_code == 200, response.text
        run_id = response.json()["id"]

        status_response = client.get(f"/ingestion_runs/{run_id}")
        assert status_response.status_code == 200, status_response.text
        payload = status_response.json()
        assert payload["status"] == "completed"
        assert payload["error_message"] is None
        assert any("Google Trends fetch failed: The read operation timed out" in flag for flag in payload["guardrail_flags"])


def test_analysis_with_no_confirmed_trends_skips_trend_exploration_insert(test_database, monkeypatch) -> None:
    monkeypatch.setattr(graph_llm, "get_chat_model", lambda *args, **kwargs: WatchOnlySynthChatModel())

    with TestClient(app) as client:
        ingestion_response = client.post(
            "/ingestion_runs",
            json={
                "market": "HK",
                "category": "skincare",
                "recent_days": 7,
                "sources": ["google_trends", "sales"],
                "target_keywords": ["niacinamide"],
                "suggested_keywords": ["niacinamide"],
            },
        )
        assert ingestion_response.status_code == 200

        analysis_response = client.post(
            "/analysis_runs",
            json={
                "market": "HK",
                "category": "skincare",
                "recency_days": 14,
                "analysis_mode": "single_market",
                "query": "Show emerging barrier repair signals in HK.",
            },
        )
        assert analysis_response.status_code == 200

        payload = client.get(f"/analysis_runs/{analysis_response.json()['id']}").json()
        assert payload["status"] == "completed"
        assert payload["report"]["trends"] == []
        assert payload["report"]["watch_list"]
        assert any("intentionally left empty" in flag for flag in payload["report"]["guardrail_flags"])
        assert payload["node_outputs"]["memory_write"]["emitted_state"]["persisted"] is False
        assert payload["node_outputs"]["memory_write"]["received_state"]["confirmed_trend_count"] == 0
        assert payload["node_outputs"]["confidence_gate"]["emitted_state"]["route"].startswith("formatter")
        assert any(
            invocation["tool"] == "memory.write" and invocation["output_summary"] == "skipped insert (no confirmed trends)"
            for invocation in payload["tool_invocations"]
        )

    with connection_scope() as connection:
        row = connection.execute("SELECT COUNT(*) AS count FROM trend_exploration WHERE market = ?", ("HK",)).fetchone()
    assert row["count"] == 0


def test_db_browser_lists_tables_schema_and_filtered_rows(test_database) -> None:
    with TestClient(app) as client:
        ingestion_response = client.post(
            "/ingestion_runs",
            json={
                "market": "HK",
                "category": "skincare",
                "recent_days": 7,
                "sources": ["sales"],
            },
        )
        assert ingestion_response.status_code == 200
        batch_id = ingestion_response.json()["source_batch_id"]

        tables_response = client.get("/db/tables")
        assert tables_response.status_code == 200
        table_names = {table["name"] for table in tables_response.json()["tables"]}
        assert {"ingestion_runs", "analysis_runs", "sales_data", "social_posts"} <= table_names

        schema_response = client.get("/db/tables/ingestion_runs/schema")
        assert schema_response.status_code == 200
        schema_names = {column["name"] for column in schema_response.json()["columns"]}
        assert {"id", "status", "source_batch_id"} <= schema_names

        rows_response = client.get(
            "/db/tables/ingestion_runs/rows",
            params={"column": "source_batch_id", "search": batch_id},
        )
        assert rows_response.status_code == 200, rows_response.text
        payload = rows_response.json()
        assert payload["total"] >= 1
        assert any(row["source_batch_id"] == batch_id for row in payload["rows"])

        invalid_sort = client.get("/db/tables/ingestion_runs/rows", params={"order_by": "guardrail_flags"})
        assert invalid_sort.status_code == 400


def test_ingestion_populates_post_trend_signals_for_social_posts(test_database, monkeypatch) -> None:
    ingestion_service.settings.tikhub_api_key = "test-key"
    ingestion_service.instagram_client.settings.tikhub_api_key = "test-key"
    ingestion_service.tiktok_photo_client.settings.tikhub_api_key = "test-key"

    def fake_instagram_fetch(*, keyword: str, feed_type: str = "top", client=None, source_batch_id: str | None = None):
        upsert_instagram_posts(
            [
                {
                    "post_id": f"ig-{keyword}",
                    "search_keyword": keyword,
                    "code": f"code-{keyword}",
                    "username": "creator",
                    "full_name": "Creator Name",
                    "caption": "New collagen gummy launch that I need to try.",
                    "hashtags_json": json.dumps(["collagen", "beauty"]),
                    "mentions_json": json.dumps([]),
                    "likes": 120,
                    "comments": 14,
                    "views": 640,
                    "is_video": 0,
                    "created_at": "2026-04-01T10:00:00",
                    "location_name": "Singapore",
                    "city": "Singapore",
                    "lat": 1.29,
                    "lng": 103.85,
                    "source_batch_id": source_batch_id,
                }
            ]
        )
        return {}, [], 1

    def fake_tiktok_fetch(*, keyword: str, count: int = 20, offset: int = 0, search_id=None, cookie=None, client=None, source_batch_id: str | None = None):
        upsert_tiktok_photo_posts(
            [
                {
                    "id": f"tt-{keyword}",
                    "search_keyword": keyword,
                    "create_time_unix": 1712000000,
                    "create_time": "2026-04-01 10:00:00",
                    "description": "Viral scalp serum everyone wants to try.",
                    "author_json": json.dumps({"nickname": "tester"}),
                    "image_url": "https://example.com/image.jpg",
                    "cover_url": "https://example.com/cover.jpg",
                    "stats_json": json.dumps({"likes": 882, "comments": 46, "shares": 14, "plays": 60400, "collects": 79}),
                    "hashtags_json": json.dumps(["scalp", "serum"]),
                    "music_json": None,
                    "is_ad": 0,
                    "share_url": "https://www.tiktok.com/photo/tt-collagen",
                    "source_batch_id": source_batch_id,
                }
            ]
        )
        return {}, [], 1

    monkeypatch.setattr(ingestion_module, "run_instagram_fetch_clean_save", fake_instagram_fetch)
    monkeypatch.setattr(ingestion_module, "run_tiktok_photo_fetch_clean_save", fake_tiktok_fetch)

    with TestClient(app) as client:
        response = client.post(
            "/ingestion_runs",
            json={
                "market": "SG",
                "category": "supplements",
                "recent_days": 7,
                "sources": ["instagram", "tiktok"],
                "target_keywords": ["collagen"],
                "suggested_keywords": ["collagen"],
            },
        )
        assert response.status_code == 200, response.text
        run_id = response.json()["id"]

        status_response = client.get(f"/ingestion_runs/{run_id}")
        assert status_response.status_code == 200, status_response.text
        status_payload = status_response.json()
        assert status_payload["status"] == "completed"
        assert status_payload["stats"]["post_signal_rows"] == 2

        tables_response = client.get("/db/tables")
        assert tables_response.status_code == 200
        table_names = {table["name"] for table in tables_response.json()["tables"]}
        assert "post_trend_signals" in table_names

        rows_response = client.get("/db/tables/post_trend_signals/rows")
        assert rows_response.status_code == 200, rows_response.text
        rows_payload = rows_response.json()
        assert rows_payload["total"] == 2
        assert {row["source_table"] for row in rows_payload["rows"]} == {"instagram_posts", "tiktok_photo_posts"}
        assert {row["category"] for row in rows_payload["rows"]} <= {"skincare", "haircare", "makeup", "supplement"}
        assert any(row["category"] == "supplement" for row in rows_payload["rows"])


def test_recent_run_list_endpoints_return_paginated_items(test_database) -> None:
    with TestClient(app) as client:
        ingestion_response = client.post(
            "/ingestion_runs",
            json={
                "market": "HK",
                "category": "skincare",
                "recent_days": 7,
                "sources": ["sales"],
            },
        )
        assert ingestion_response.status_code == 200

        analysis_response = client.post(
            "/analysis_runs",
            json={
                "market": "HK",
                "category": "skincare",
                "recency_days": 14,
                "analysis_mode": "single_market",
            },
        )
        assert analysis_response.status_code == 200

        ingestion_runs = client.get("/ingestion_runs")
        assert ingestion_runs.status_code == 200
        ingestion_payload = ingestion_runs.json()
        assert ingestion_payload["total"] >= 1
        assert len(ingestion_payload["items"]) >= 1
        assert ingestion_payload["items"][0]["id"]

        analysis_runs = client.get("/analysis_runs")
        assert analysis_runs.status_code == 200
        analysis_payload = analysis_runs.json()
        assert analysis_payload["total"] >= 1
        assert len(analysis_payload["items"]) >= 1
        assert analysis_payload["items"][0]["execution_trace"] is not None


def test_analysis_stream_endpoint_returns_incremental_backend_updates(test_database) -> None:
    with TestClient(app) as client:
        ingestion_response = client.post(
            "/ingestion_runs",
            json={
                "market": "HK",
                "category": "skincare",
                "recent_days": 7,
                "sources": ["google_trends", "sales"],
                "target_keywords": ["niacinamide"],
            },
        )
        assert ingestion_response.status_code == 200

        response = client.post(
            "/analysis_runs/stream",
            json={
                "market": "HK",
                "category": "skincare",
                "recency_days": 14,
                "analysis_mode": "single_market",
                "query": "Focus on barrier repair ingredients in HK.",
            },
        )
        assert response.status_code == 200, response.text

        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        assert events[0]["type"] == "run.created"
        assert any(event["type"] == "run.updated" for event in events)
        assert any(
            "[BackendData]" in trace_line
            for event in events
            for trace_line in event["run"].get("execution_trace", [])
        )
        assert events[-1]["type"] == "run.completed"
        assert events[-1]["run"]["report"]["market"] == "HK"
        intent_invocation = next(
            invocation
            for invocation in events[-1]["run"].get("tool_invocations", [])
            if invocation["tool"] == "llm.intent_parser"
        )
        assert "search_trends" in intent_invocation["user_prompt"]
        assert "sales_data" in intent_invocation["user_prompt"]
        assert "post_trend_signals" in intent_invocation["user_prompt"]
