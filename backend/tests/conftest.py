from __future__ import annotations

from collections.abc import Iterator
import json
import re

import pytest

from app.api.routes.ingestion import service as ingestion_service
from app.core.config import get_settings
from app.db.migrator import apply_migrations
from app.graph import llm as graph_llm


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


class FakeStructuredInvoker:
    def __init__(self, schema: type) -> None:
        self.schema = schema

    def invoke(self, payload: object):
        text = _message_text(payload)
        schema_name = getattr(self.schema, "__name__", "")

        if schema_name == "QueryIntent":
            market_match = re.search(r"requested_market:\s*(\w+)", text)
            requested_market = market_match.group(1) if market_match else "HK"
            category_match = re.search(r"requested_category:\s*(\w+)", text)
            requested_category = category_match.group(1) if category_match else "skincare"
            recency_match = re.search(r"requested_recency_days:\s*(\d+)", text)
            requested_recency = int(recency_match.group(1)) if recency_match else 14
            mode_match = re.search(r"requested_analysis_mode:\s*(\w+)", text)
            analysis_mode = mode_match.group(1) if mode_match else "single_market"
            if requested_market == "cross" or analysis_mode == "cross_market":
                markets = ["HK", "KR", "TW", "SG"]
            else:
                markets = [requested_market]
            return self.schema.model_validate(
                {
                    "markets": markets,
                    "category": requested_category,
                    "recency_days": requested_recency,
                    "entity_types": ["ingredient", "brand", "function"],
                    "analysis_mode": analysis_mode,
                    "focus_hint": None,
                }
            )

        if schema_name == "LensCandidateBatch":
            terms = _extract_terms(text)[:5] or ["niacinamide", "ceramide", "cica"]
            candidates = [
                {
                    "canonical_term": term,
                    "entity_type": "ingredient",
                    "lens": "Momentum",
                    "data_pattern": f"{term} shows multiple reinforcing rows in the provided market slice.",
                    "viral_reasoning": f"{term} is appearing across more than one signal, which suggests momentum instead of isolated noise.",
                    "strongest_signal": "social",
                    "weakest_signal": "sales",
                    "self_confidence": "medium",
                }
                for term in terms
            ]
            return self.schema.model_validate({"candidates": candidates})

        if schema_name == "SynthesizerVerdictBatch":
            terms = _extract_terms(text)
            verdicts = []
            for index, term in enumerate(terms):
                verdicts.append(
                    {
                        "canonical_term": term,
                        "status": "confirmed" if index < 3 else "watch",
                        "challenge_notes": [f"{term} has multi-signal support in the canned test verdict."],
                        "hype_only": False,
                        "seasonal_risk": False,
                    }
                )
            return self.schema.model_validate({"verdicts": verdicts})

        if schema_name == "TrendNarrative":
            term = _extract_terms(text)[0] if _extract_terms(text) else "trend"
            return self.schema.model_validate({"summary": f"{term} shows enough aligned evidence to merit attention."})

        raise AssertionError(f"Unhandled fake structured schema: {schema_name}")


class FakeChatResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChatModel:
    def invoke(self, payload: object) -> FakeChatResponse:
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
            return FakeChatResponse(
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
            return FakeChatResponse(
                json.dumps(
                    {
                        "candidates": [
                            {
                                "canonical_term": term,
                                "entity_type": "ingredient",
                                "lens": "Momentum",
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
            return FakeChatResponse(
                json.dumps(
                    {
                        "verdicts": [
                            {
                                "canonical_term": term,
                                "status": "confirmed" if index < 3 else "watch",
                                "challenge_notes": [f"{term} has multi-signal support in the canned test verdict."],
                                "hype_only": False,
                                "seasonal_risk": False,
                            }
                            for index, term in enumerate(terms)
                        ]
                    }
                )
            )

        return FakeChatResponse("Ok")

    def with_structured_output(self, schema: type) -> FakeStructuredInvoker:
        return FakeStructuredInvoker(schema)


@pytest.fixture(autouse=True)
def fake_graph_llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(graph_llm, "get_chat_model", lambda *args, **kwargs: FakeChatModel())
    yield


@pytest.fixture()
def test_database(tmp_path) -> Iterator[None]:
    get_settings.cache_clear()
    settings = get_settings()
    original_path = settings.database_path
    original_tikhub = settings.tikhub_api_key
    original_openrouter = settings.openrouter_api_key
    original_light_model = settings.light_model
    settings.database_path = tmp_path / "test.sqlite"
    settings.tikhub_api_key = None
    settings.openrouter_api_key = None

    apply_migrations()

    ingestion_service.settings = settings
    ingestion_service.tiktok_photo_client.settings = settings
    ingestion_service.instagram_client.settings = settings
    ingestion_service.serpapi_client.settings = settings
    ingestion_service.enrichment_service.settings = settings
    try:
        yield
    finally:
        settings.database_path = original_path
        settings.tikhub_api_key = original_tikhub
        settings.openrouter_api_key = original_openrouter
        settings.light_model = original_light_model
        get_settings.cache_clear()
