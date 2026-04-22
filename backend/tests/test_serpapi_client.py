from __future__ import annotations

from typing import Any

from app.services.ingestion import serpapi_client as serpapi_module
from app.services.ingestion.serpapi_client import SerpApiClient


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    last_params: dict[str, Any] | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url: str, params: dict[str, Any]) -> _FakeResponse:
        _FakeClient.last_params = {"url": url, **params}
        return _FakeResponse(
            {
                "search_metadata": {
                    "id": "695928708c24bd247f1be805",
                    "status": "Success",
                },
                "search_parameters": {
                    "engine": "google_trends",
                    "q": "quantum computing",
                    "hl": "en",
                    "date": "today 12-m",
                    "tz": "420",
                    "data_type": "TIMESERIES",
                },
                "interest_over_time": {
                    "timeline_data": [
                        {
                            "date": "Dec 29, 2024 - Jan 4, 2025",
                            "timestamp": "1735430400",
                            "values": [
                                {
                                    "query": "quantum computing",
                                    "value": "8",
                                    "extracted_value": 8,
                                }
                            ],
                        },
                        {
                            "date": "Jan 5, 2025 - Jan 11, 2025",
                            "timestamp": "1736035200",
                            "values": [
                                {
                                    "query": "quantum computing",
                                    "value": "12",
                                    "extracted_value": 12,
                                }
                            ],
                        },
                    ]
                },
            }
        )


def test_fetch_trends_parses_documented_serpapi_timeseries_payload(monkeypatch) -> None:
    monkeypatch.setattr(serpapi_module.httpx, "Client", _FakeClient)
    client = SerpApiClient()
    client.settings.serpapi_api_key = "test-key"

    rows = client.fetch_trends(
        market="HK",
        category="skincare",
        recent_days=30,
        seed_terms=["quantum computing"],
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["keyword"] == "quantum computing"
    assert row["geo"] == "HK"
    assert row["index_value"] == 12.0
    assert row["source"] == "serpapi"
    assert row["raw_timeseries"] == [
        {
            "date": "Dec 29, 2024 - Jan 4, 2025",
            "timestamp": "1735430400",
            "query": "quantum computing",
            "value": "8",
            "extracted_value": 8.0,
        },
        {
            "date": "Jan 5, 2025 - Jan 11, 2025",
            "timestamp": "1736035200",
            "query": "quantum computing",
            "value": "12",
            "extracted_value": 12.0,
        },
    ]
    assert _FakeClient.last_params is not None
    assert _FakeClient.last_params["url"] == "https://serpapi.com/search"
    assert _FakeClient.last_params["engine"] == "google_trends"
    assert _FakeClient.last_params["data_type"] == "TIMESERIES"
    assert _FakeClient.last_params["date"] == "today 1-m"
    assert _FakeClient.last_params["tz"] == "-480"
