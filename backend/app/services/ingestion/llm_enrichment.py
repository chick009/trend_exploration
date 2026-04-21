from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re

import httpx

from app.core.config import get_settings
from app.db.repository import get_entity_dictionary


POSITIVE_TERMS = {
    "love",
    "glow",
    "bright",
    "hydrating",
    "calming",
    "viral",
    "obsessed",
    "effective",
    "favorite",
    "gentle",
}
NEGATIVE_TERMS = {
    "irritating",
    "breakout",
    "drying",
    "pricey",
    "sticky",
    "harsh",
    "bad",
    "worse",
}

SUBCATEGORY_KEYWORDS = {
    "skincare": {
        "serum": "serums",
        "cream": "creams",
        "essence": "essences",
        "toner": "toners",
        "spf": "sun care",
    },
    "haircare": {
        "scalp": "scalp care",
        "hair": "hair treatment",
        "tonic": "tonics",
    },
    "makeup": {
        "lip": "lip makeup",
        "foundation": "base makeup",
        "blush": "cheek makeup",
    },
    "supplements": {
        "collagen": "beauty supplements",
        "gummy": "beauty supplements",
    },
}


@dataclass
class EnrichmentResult:
    llm_category: str
    llm_subcategory: str
    positivity_score: float
    sentiment_label: str
    relevance_score: float
    llm_entities: list[str]
    llm_summary: str
    processing_model: str
    processed_at: str


class LLMEnrichmentService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.entity_dictionary: dict[str, dict] | None = None

    def enrich_text(
        self,
        *,
        text: str,
        category_hint: str | None = None,
        explicit_entities: list[str] | None = None,
    ) -> EnrichmentResult:
        if self.entity_dictionary is None:
            self.entity_dictionary = get_entity_dictionary()
        llm_result = self._openrouter_enrich_text(
            text=text,
            category_hint=category_hint,
            explicit_entities=explicit_entities or [],
        )
        if llm_result is not None:
            return llm_result
        return self._heuristic_enrich_text(
            text=text,
            category_hint=category_hint,
            explicit_entities=explicit_entities,
        )

    def _heuristic_enrich_text(
        self,
        *,
        text: str,
        category_hint: str | None = None,
        explicit_entities: list[str] | None = None,
    ) -> EnrichmentResult:
        normalized = text.lower()
        entities = set(explicit_entities or [])
        inferred_category = category_hint if category_hint and category_hint != "all" else "skincare"
        subcategory = "general"

        for canonical, metadata in self.entity_dictionary.items():
            aliases = [canonical, *metadata["aliases"]]
            if any(alias.lower() in normalized for alias in aliases):
                entities.add(canonical)
                if category_hint in (None, "all") and metadata["hb_category"]:
                    inferred_category = metadata["hb_category"]

        for category, keywords in SUBCATEGORY_KEYWORDS.items():
            for term, mapped_subcategory in keywords.items():
                if term in normalized:
                    inferred_category = category if category_hint in (None, "all") else category_hint
                    subcategory = mapped_subcategory
                    break

        positive_hits = sum(term in normalized for term in POSITIVE_TERMS)
        negative_hits = sum(term in normalized for term in NEGATIVE_TERMS)
        positivity_score = max(0.0, min(1.0, 0.5 + (positive_hits - negative_hits) * 0.12))
        relevance_boost = 0.2 if entities else 0.0
        relevance_boost += 0.2 if subcategory != "general" else 0.0
        relevance_score = max(0.0, min(1.0, 0.4 + relevance_boost + positive_hits * 0.05))
        sentiment_label = "positive" if positivity_score >= 0.6 else "negative" if positivity_score <= 0.4 else "mixed"

        if not entities and category_hint not in (None, "all"):
            relevance_score = max(relevance_score, 0.55)

        summary = self._build_summary(
            category=inferred_category,
            subcategory=subcategory,
            entities=sorted(entities),
            positivity_score=positivity_score,
        )
        return EnrichmentResult(
            llm_category=inferred_category,
            llm_subcategory=subcategory,
            positivity_score=positivity_score,
            sentiment_label=sentiment_label,
            relevance_score=relevance_score,
            llm_entities=sorted(entities),
            llm_summary=summary,
            processing_model="heuristic-enricher-v1",
            processed_at=datetime.utcnow().isoformat(),
        )

    def _openrouter_enrich_text(
        self,
        *,
        text: str,
        category_hint: str | None,
        explicit_entities: list[str],
    ) -> EnrichmentResult | None:
        if not self.settings.openrouter_api_key:
            return None

        categories = ["skincare", "haircare", "makeup", "supplements", "all"]
        prompt = f"""
You are classifying Health & Beauty retail social/search text.
Return strict JSON only with this schema:
{{
  "llm_category": "skincare|haircare|makeup|supplements|all",
  "llm_subcategory": "short string",
  "positivity_score": 0.0,
  "sentiment_label": "positive|mixed|negative",
  "relevance_score": 0.0,
  "llm_entities": ["canonical terms only when clearly present"],
  "llm_summary": "one concise sentence"
}}

Rules:
- Keep scores between 0 and 1.
- Use the category hint when it fits, but do not force it if the text clearly belongs elsewhere.
- Prefer canonical entities already known in the text.
- Do not wrap the JSON in markdown.

Category hint: {category_hint or "none"}
Explicit entities: {json.dumps(explicit_entities)}
Allowed categories: {json.dumps(categories)}
Text:
\"\"\"{text[:5000]}\"\"\"
""".strip()

        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "trend-exploration-mvp",
        }
        payload = {
            "model": self.settings.openrouter_model,
            "messages": [
                {"role": "system", "content": "You return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }

        try:
            with httpx.Client(base_url=self.settings.openrouter_base_url, timeout=30) as client:
                response = client.post("/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = self._parse_json_payload(content)
            return EnrichmentResult(
                llm_category=str(parsed.get("llm_category") or category_hint or "skincare"),
                llm_subcategory=str(parsed.get("llm_subcategory") or "general"),
                positivity_score=self._clamp_score(parsed.get("positivity_score"), default=0.5),
                sentiment_label=str(parsed.get("sentiment_label") or "mixed"),
                relevance_score=self._clamp_score(parsed.get("relevance_score"), default=0.5),
                llm_entities=[str(entity) for entity in parsed.get("llm_entities", [])][:10],
                llm_summary=str(parsed.get("llm_summary") or "OpenRouter enrichment completed."),
                processing_model=self.settings.openrouter_model,
                processed_at=datetime.utcnow().isoformat(),
            )
        except Exception:
            return None

    def enrich_keyword(self, keyword: str, category_hint: str | None = None) -> EnrichmentResult:
        return self.enrich_text(text=keyword, category_hint=category_hint)

    def _parse_json_payload(self, content: str) -> dict:
        content = content.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, flags=re.DOTALL)
        if fenced:
            content = fenced.group(1)
        return json.loads(content)

    def _clamp_score(self, value: object, *, default: float) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return default

    def _build_summary(
        self,
        *,
        category: str,
        subcategory: str,
        entities: list[str],
        positivity_score: float,
    ) -> str:
        tone = "strongly positive" if positivity_score > 0.7 else "mixed-to-positive" if positivity_score > 0.5 else "neutral"
        entity_text = ", ".join(entities[:3]) if entities else "no strong canonical entity"
        return (
            f"Classified as {category}/{subcategory}. The batch content shows {tone} community language "
            f"and references {entity_text}."
        )
