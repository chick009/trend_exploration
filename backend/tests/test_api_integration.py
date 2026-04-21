from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


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
            },
        )
    assert response.status_code == 200, response.text


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
                "sources": ["rednote", "google_trends", "sales"],
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

        latest_response = client.get("/trends/latest", params={"market": "HK", "category": "skincare"})
        assert latest_response.status_code == 200


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
