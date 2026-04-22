from __future__ import annotations

from app.core.config import get_settings
from app.models.schemas import KeywordSuggestionRequest, SuggestedKeyword
from app.services.ingestion import keyword_suggestion_service as suggestion_module
from app.services.ingestion.keyword_suggestion_service import KeywordSuggestionBatch, KeywordSuggestionService


def test_keyword_suggestions_use_light_model(monkeypatch) -> None:
    settings = get_settings()
    settings.light_model = "fast-keyword-model"

    captured: dict[str, str | None] = {"model": None}

    def fake_invoke_json_response(schema, *, user_prompt: str, system_prompt: str, model: str | None = None):
        captured["model"] = model
        return KeywordSuggestionBatch(
            suggestions=[
                SuggestedKeyword(keyword="niacinamide serum", rationale="High-intent ingredient phrase."),
            ]
        )

    monkeypatch.setattr(suggestion_module, "invoke_json_response", fake_invoke_json_response)

    service = KeywordSuggestionService()
    response = service.suggest_keywords(
        KeywordSuggestionRequest(
            market="HK",
            category="skincare",
            recent_days=7,
            sources=["google_trends", "instagram"],
            max_target_keywords=5,
        )
    )

    assert captured["model"] == "fast-keyword-model"
    assert response.suggestions
    assert response.suggestions[0].keyword == "niacinamide serum"
