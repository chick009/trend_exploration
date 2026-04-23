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
TREND_SIGNAL_TERMS = {
    "trend",
    "viral",
    "trending",
    "must-have",
    "must try",
    "favorite",
    "obsessed",
    "bestseller",
    "everyone",
}
NOVELTY_TERMS = {
    "new",
    "launch",
    "just dropped",
    "latest",
    "first",
    "innovative",
    "breakthrough",
    "next-gen",
    "emerging",
}
INTENT_TERMS = {
    "need",
    "buy",
    "bought",
    "add to cart",
    "purchase",
    "repurchase",
    "try this",
    "want this",
    "worth it",
}
POST_SIGNAL_REGIONS = ("HK", "KR", "TW", "SG", "cross")
POST_SIGNAL_CATEGORIES = ("skincare", "haircare", "makeup", "supplement")
REGION_KEYWORDS = {
    "HK": {"hk", "hong kong", "hongkong"},
    "KR": {"kr", "korea", "korean", "seoul", "k-beauty", "kbeauty"},
    "TW": {"tw", "taiwan", "taipei"},
    "SG": {"sg", "singapore"},
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


@dataclass
class PostSignalResult:
    region: str
    category: str
    trend_strength: float
    novelty: float
    consumer_intent: float
    rationale: str
    processing_model: str
    processed_at: str

    def as_row(self) -> dict[str, Any]:
        return {
            "region": self.region,
            "category": self.category,
            "trend_strength": self.trend_strength,
            "novelty": self.novelty,
            "consumer_intent": self.consumer_intent,
            "llm_rationale": self.rationale,
            "processing_model": self.processing_model,
            "processed_at": self.processed_at,
        }


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

    def score_post(
        self,
        *,
        text: str,
        market_hint: str | None = None,
        category_hint: str | None = None,
    ) -> PostSignalResult:
        if self.entity_dictionary is None:
            self.entity_dictionary = get_entity_dictionary()
        llm_result = self._openrouter_score_post(
            text=text,
            market_hint=market_hint,
            category_hint=category_hint,
        )
        if llm_result is not None:
            return llm_result
        return self._heuristic_score_post(
            text=text,
            market_hint=market_hint,
            category_hint=category_hint,
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
            llm_category=self._normalize_hb_category(inferred_category, category_hint=category_hint),
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
                llm_category=self._normalize_hb_category(parsed.get("llm_category"), category_hint=category_hint),
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

    def _heuristic_score_post(
        self,
        *,
        text: str,
        market_hint: str | None = None,
        category_hint: str | None = None,
    ) -> PostSignalResult:
        normalized = text.lower()
        category = self._normalize_signal_category(
            self._infer_post_category(normalized, category_hint),
            category_hint=category_hint,
        )
        region = self._normalize_signal_region(
            self._infer_post_region(normalized, market_hint),
            market_hint=market_hint,
        )
        entity_hits = self._count_entity_hits(normalized)
        trend_hits = sum(term in normalized for term in TREND_SIGNAL_TERMS)
        novelty_hits = sum(term in normalized for term in NOVELTY_TERMS)
        intent_hits = sum(term in normalized for term in INTENT_TERMS)
        positive_hits = sum(term in normalized for term in POSITIVE_TERMS)
        negative_hits = sum(term in normalized for term in NEGATIVE_TERMS)

        trend_strength = self._clamp_score(
            0.35 + trend_hits * 0.12 + entity_hits * 0.06 + positive_hits * 0.04 - negative_hits * 0.08,
            default=0.35,
        )
        novelty = self._clamp_score(
            0.2 + novelty_hits * 0.16 + entity_hits * 0.03,
            default=0.2,
        )
        consumer_intent = self._clamp_score(
            0.18 + intent_hits * 0.18 + positive_hits * 0.05 - negative_hits * 0.05,
            default=0.18,
        )

        rationale_bits = [
            f"classified as {category}",
            f"assigned to {region}",
        ]
        if trend_hits or novelty_hits or intent_hits:
            rationale_bits.append(
                "based on "
                + ", ".join(
                    part
                    for part, hit_count in (
                        ("trend language", trend_hits),
                        ("novelty cues", novelty_hits),
                        ("consumer-intent wording", intent_hits),
                    )
                    if hit_count
                )
            )
        elif entity_hits:
            rationale_bits.append("based on known beauty entities in the post")
        else:
            rationale_bits.append("using market/category hints because the text is sparse")

        return PostSignalResult(
            region=region,
            category=category,
            trend_strength=trend_strength,
            novelty=novelty,
            consumer_intent=consumer_intent,
            rationale=". ".join(rationale_bits).strip().rstrip(".") + ".",
            processing_model="heuristic-post-scorer-v1",
            processed_at=datetime.utcnow().isoformat(),
        )

    def _openrouter_score_post(
        self,
        *,
        text: str,
        market_hint: str | None,
        category_hint: str | None,
    ) -> PostSignalResult | None:
        if not self.settings.openrouter_api_key:
            return None

        prompt = f"""
You classify beauty and personal-care social posts into a structured trend-signal record.
Return strict JSON only with this schema:
{{
  "region": "HK|KR|TW|SG|cross",
  "category": "skincare|haircare|makeup|supplement",
  "trend_strength": 0.0,
  "novelty": 0.0,
  "consumer_intent": 0.0,
  "rationale": "one concise sentence"
}}

Rules:
- Scores must be numbers between 0 and 1.
- Use market_hint only as a soft hint, not as a forced answer.
- If no specific market is clear, return "cross".
- Category must be one of skincare, haircare, makeup, supplement.
- Prefer evidence from the text over defaults.
- Do not wrap the JSON in markdown.

market_hint: {market_hint or "none"}
category_hint: {category_hint or "none"}
text:
\"\"\"{text[:5000]}\"\"\"
""".strip()

        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "trend-exploration-mvp",
        }
        payload = {
            "model": self.settings.resolved_light_model(),
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
            return PostSignalResult(
                region=self._normalize_signal_region(parsed.get("region"), market_hint=market_hint),
                category=self._normalize_signal_category(parsed.get("category"), category_hint=category_hint),
                trend_strength=self._clamp_score(parsed.get("trend_strength"), default=0.5),
                novelty=self._clamp_score(parsed.get("novelty"), default=0.35),
                consumer_intent=self._clamp_score(parsed.get("consumer_intent"), default=0.35),
                rationale=str(parsed.get("rationale") or "LLM trend-signal scoring completed."),
                processing_model=self.settings.resolved_light_model(),
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

    def _normalize_signal_region(self, value: object, *, market_hint: str | None) -> str:
        if isinstance(value, str):
            cleaned = value.strip()
            upper = cleaned.upper()
            if upper in POST_SIGNAL_REGIONS:
                return upper
            if cleaned.lower() == "cross":
                return "cross"
        if market_hint in POST_SIGNAL_REGIONS:
            return str(market_hint)
        return "cross"

    def _normalize_signal_category(self, value: object, *, category_hint: str | None) -> str:
        mapped = self._map_category_value(value)
        if mapped:
            return mapped
        hint_mapped = self._map_category_value(category_hint)
        if hint_mapped:
            return hint_mapped
        return "skincare"

    def _normalize_hb_category(self, value: object, *, category_hint: str | None) -> str:
        mapped = self._map_hb_category_value(value)
        if mapped:
            return mapped
        hint_mapped = self._map_hb_category_value(category_hint)
        if hint_mapped:
            return hint_mapped
        return "skincare"

    def _map_hb_category_value(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = value.strip().lower()
        if not cleaned or cleaned == "all":
            return None

        direct_aliases = {
            "supplement": "supplements",
            "supplements": "supplements",
            "beauty supplement": "supplements",
            "beauty supplements": "supplements",
        }
        if cleaned in direct_aliases:
            return direct_aliases[cleaned]
        if cleaned in {"skincare", "haircare", "makeup"}:
            return cleaned

        tokens = [token.strip() for token in re.split(r"[,;/|]", cleaned) if token.strip()]
        for token in tokens:
            mapped = direct_aliases.get(token)
            if mapped:
                return mapped
            if token in {"skincare", "haircare", "makeup"}:
                return token

        for category in ("skincare", "haircare", "makeup", "supplement", "supplements"):
            if re.search(rf"\b{re.escape(category)}\b", cleaned):
                return direct_aliases.get(category, category)
        return None

    def _map_category_value(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = value.strip().lower()
        if cleaned in POST_SIGNAL_CATEGORIES:
            return cleaned
        category_aliases = {
            "supplements": "supplement",
            "supplements ": "supplement",
            "beauty supplement": "supplement",
            "beauty supplements": "supplement",
        }
        if cleaned in category_aliases:
            return category_aliases[cleaned]
        if cleaned == "all":
            return None
        return None

    def _infer_post_region(self, normalized_text: str, market_hint: str | None) -> str:
        matches = [
            region
            for region, keywords in REGION_KEYWORDS.items()
            if any(keyword in normalized_text for keyword in keywords)
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return "cross"
        if market_hint in POST_SIGNAL_REGIONS:
            return str(market_hint)
        return "cross"

    def _infer_post_category(self, normalized_text: str, category_hint: str | None) -> str:
        inferred_category = self._map_category_value(category_hint) or "skincare"
        for category, keywords in SUBCATEGORY_KEYWORDS.items():
            mapped_category = self._map_category_value(category) or category
            for term in keywords:
                if term in normalized_text:
                    return mapped_category
        category_terms = {
            "skincare": {"skin", "serum", "cream", "toner", "spf", "moisturizer", "essence"},
            "haircare": {"hair", "scalp", "shampoo", "conditioner", "mask", "treatment"},
            "makeup": {"lip", "foundation", "blush", "mascara", "eyeliner", "concealer"},
            "supplement": {"supplement", "collagen", "gummy", "capsule", "powder", "vitamin"},
        }
        for category, keywords in category_terms.items():
            if any(keyword in normalized_text for keyword in keywords):
                return category
        return inferred_category

    def _count_entity_hits(self, normalized_text: str) -> int:
        hit_count = 0
        for canonical, metadata in self.entity_dictionary.items():
            aliases = [canonical, *metadata["aliases"]]
            if any(alias.lower() in normalized_text for alias in aliases):
                hit_count += 1
        return hit_count
