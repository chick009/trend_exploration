from __future__ import annotations

from typing import Any

from app.db.bootstrap import seed_reference_data
from app.db.migrator import apply_migrations
from app.services.ingestion import llm_enrichment as enrichment_module
from app.services.ingestion.llm_enrichment import LLMEnrichmentService


def test_enrichment_extracts_entities_and_sentiment(test_database) -> None:
    apply_migrations()
    seed_reference_data()
    service = LLMEnrichmentService()

    result = service.enrich_text(
        text="I love this niacinamide serum for glass skin. The finish is glowy and gentle.",
        category_hint="skincare",
    )

    assert result.llm_category == "skincare"
    assert "niacinamide" in result.llm_entities
    assert result.positivity_score > 0.5
    assert result.relevance_score >= 0.55


def test_score_post_normalizes_supplement_category_and_market_hint(test_database) -> None:
    apply_migrations()
    seed_reference_data()
    service = LLMEnrichmentService()

    result = service.score_post(
        text="New collagen gummy launch that I need to try.",
        market_hint="SG",
        category_hint="supplements",
    )

    assert result.region == "SG"
    assert result.category == "supplement"
    assert 0.0 <= result.trend_strength <= 1.0
    assert 0.0 <= result.novelty <= 1.0
    assert 0.0 <= result.consumer_intent <= 1.0


def test_score_post_uses_light_model_when_configured(test_database, monkeypatch) -> None:
    apply_migrations()
    seed_reference_data()
    service = LLMEnrichmentService()
    service.settings.openrouter_api_key = "fake-key"
    service.settings.light_model = "fast-post-model"

    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"region":"SG","category":"supplement","trend_strength":0.7,'
                                '"novelty":0.4,"consumer_intent":0.9,"rationale":"Fast model response."}'
                            )
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, path: str, *, headers: dict[str, str], json: dict[str, Any]) -> FakeResponse:
            captured["path"] = path
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(enrichment_module.httpx, "Client", FakeClient)

    result = service.score_post(
        text="New collagen gummy launch that I need to try.",
        market_hint="SG",
        category_hint="supplements",
    )

    assert captured["path"] == "/chat/completions"
    assert captured["json"]["model"] == "fast-post-model"
    assert result.processing_model == "fast-post-model"
    assert result.region == "SG"


def test_enrich_text_normalizes_openrouter_category_values(test_database, monkeypatch) -> None:
    apply_migrations()
    seed_reference_data()
    service = LLMEnrichmentService()
    service.settings.openrouter_api_key = "fake-key"

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"llm_category":"skincare, makeup","llm_subcategory":"serums",'
                                '"positivity_score":0.7,"sentiment_label":"positive","relevance_score":0.8,'
                                '"llm_entities":["niacinamide"],"llm_summary":"Normalized category."}'
                            )
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, path: str, *, headers: dict[str, str], json: dict[str, Any]) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(enrichment_module.httpx, "Client", FakeClient)

    result = service.enrich_text(
        text="Niacinamide serum is trending again.",
        category_hint="skincare",
    )

    assert result.llm_category == "skincare"
