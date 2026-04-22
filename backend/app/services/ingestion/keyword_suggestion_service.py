from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.db.repository import get_entity_dictionary
from app.graph.llm import invoke_json_response
from app.models.schemas import KeywordSuggestionRequest, KeywordSuggestionResponse, SuggestedKeyword
from app.seed.reference_data import SALES_SKU_SEEDS
from app.services.ingestion.source_capabilities import build_recency_support


class KeywordSuggestionBatch(BaseModel):
    suggestions: list[SuggestedKeyword] = Field(default_factory=list)


class KeywordSuggestionService:
    def suggest_keywords(self, request: KeywordSuggestionRequest) -> KeywordSuggestionResponse:
        recency_support = build_recency_support(request.sources)
        guardrail_flags = [
            item.detail
            for item in recency_support
            if item.status != "supported" and request.recent_days is not None
        ]

        keyword_driven_sources = [source for source in request.sources if source != "sales"]
        if not keyword_driven_sources:
            return KeywordSuggestionResponse(
                market=request.market,
                category=request.category,
                recent_days=request.recent_days,
                max_target_keywords=request.max_target_keywords,
                sources=request.sources,
                suggestions=[],
                guardrail_flags=["Sales-only extraction does not require target keywords."],
                recency_support=recency_support,
            )

        suggestions = self._llm_suggestions(request)
        if not suggestions:
            suggestions = self._fallback_suggestions(request)

        return KeywordSuggestionResponse(
            market=request.market,
            category=request.category,
            recent_days=request.recent_days,
            max_target_keywords=request.max_target_keywords,
            sources=request.sources,
            suggestions=suggestions[: request.max_target_keywords],
            guardrail_flags=guardrail_flags,
            recency_support=recency_support,
        )

    def _llm_suggestions(self, request: KeywordSuggestionRequest) -> list[SuggestedKeyword]:
        settings = get_settings()
        try:
            batch = invoke_json_response(
                KeywordSuggestionBatch,
                system_prompt=(
                    "You generate concise search keywords for health and beauty market research. "
                    "Prefer brand names, product families, hero products, ingredient phrases, and high-intent search terms. "
                    "Keep each keyword short, literal, and safe for third-party API search inputs."
                ),
                user_prompt=(
                    f"Market: {request.market}\n"
                    f"Category: {request.category}\n"
                    f"Sources: {', '.join(request.sources)}\n"
                    f"Requested recency days: {request.recent_days}\n"
                    f"Maximum keywords: {request.max_target_keywords}\n"
                    "Return a balanced list of target keywords the user can review and edit before extraction.\n"
                    "Each suggestion should include a short rationale."
                ),
                model=settings.resolved_light_model(),
            )
        except Exception:
            return []

        return self._dedupe_suggestions(batch.suggestions, limit=request.max_target_keywords)

    def _fallback_suggestions(self, request: KeywordSuggestionRequest) -> list[SuggestedKeyword]:
        entity_dictionary = get_entity_dictionary()
        bucketed: dict[str, list[SuggestedKeyword]] = defaultdict(list)

        for canonical_term, metadata in entity_dictionary.items():
            category = metadata.get("hb_category")
            if request.category != "all" and category not in {request.category, None}:
                continue

            origin_market = str(metadata.get("origin_market") or "").upper()
            entity_type = str(metadata.get("entity_type") or "keyword")
            rationale = metadata.get("description") or f"Known {entity_type} term for {request.category}."

            if request.market != "cross" and origin_market == request.market:
                priority = "market_match"
            elif entity_type == "brand":
                priority = "brand"
            elif entity_type == "product_type":
                priority = "product"
            elif entity_type == "ingredient":
                priority = "ingredient"
            else:
                priority = "other"

            bucketed[priority].append(
                SuggestedKeyword(
                    keyword=canonical_term,
                    rationale=str(rationale),
                )
            )

        for sku in SALES_SKU_SEEDS:
            if request.category != "all" and sku["category"] != request.category:
                continue
            bucketed["product"].append(
                SuggestedKeyword(
                    keyword=sku["product_name"],
                    rationale=f"Seeded sales product from the {sku['brand']} catalog.",
                )
            )
            bucketed["brand"].append(
                SuggestedKeyword(
                    keyword=sku["brand"],
                    rationale=f"Brand present in local sales seeds for {sku['category']}.",
                )
            )

        ordered: list[SuggestedKeyword] = []
        for key in ("market_match", "brand", "product", "ingredient", "other"):
            ordered.extend(bucketed.get(key, []))

        if not ordered:
            ordered = [
                SuggestedKeyword(
                    keyword=request.category if request.category != "all" else "beauty trend",
                    rationale="Generic fallback keyword because no category-specific entities were found.",
                )
            ]

        return self._dedupe_suggestions(ordered, limit=request.max_target_keywords)

    @staticmethod
    def _dedupe_suggestions(suggestions: list[SuggestedKeyword], *, limit: int) -> list[SuggestedKeyword]:
        deduped: list[SuggestedKeyword] = []
        seen: set[str] = set()
        for suggestion in suggestions:
            keyword = suggestion.keyword.strip()
            if not keyword:
                continue
            key = keyword.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(SuggestedKeyword(keyword=keyword, rationale=suggestion.rationale))
            if len(deduped) >= limit:
                break
        return deduped
