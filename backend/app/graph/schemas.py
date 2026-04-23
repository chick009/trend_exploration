from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


MarketCode = Literal["HK", "KR", "TW", "SG"]
CategoryName = Literal["skincare", "haircare", "makeup", "supplements", "all"]
EntityTypeName = Literal["ingredient", "brand", "function"]
AnalysisModeName = Literal["single_market", "cross_market"]
SignalName = Literal["social", "search", "sales", "cross_market"]
SelfConfidence = Literal["high", "medium", "low"]
TrendStatus = Literal["confirmed", "watch", "noise"]


class QueryIntent(BaseModel):
    markets: list[MarketCode] = Field(min_length=1)
    category: CategoryName = "all"
    recency_days: int = Field(default=14, ge=1, le=30)
    entity_types: list[EntityTypeName] = Field(
        default_factory=lambda: ["ingredient", "brand", "function"],
        min_length=1,
    )
    analysis_mode: AnalysisModeName = "single_market"
    focus_hint: str | None = None


class LensCandidate(BaseModel):
    canonical_term: str
    entity_type: EntityTypeName | str = "ingredient"
    lens: str
    trend_statement: str = Field(
        ...,
        description=(
            "One sentence (<= 25 words) describing the GENERAL consumer or category trend "
            "the data points to. Must not be a product, SKU, or single brand name."
        ),
    )
    data_pattern: str
    viral_reasoning: str
    strongest_signal: SignalName = "social"
    weakest_signal: SignalName = "search"
    self_confidence: SelfConfidence = "medium"


class LensCandidateBatch(BaseModel):
    candidates: list[LensCandidate] = Field(default_factory=list)


class SynthesizerVerdict(BaseModel):
    canonical_term: str
    status: TrendStatus = "watch"
    trend_statement: str | None = Field(
        default=None,
        description=(
            "Optional sharpened one-sentence trend abstraction. Keep it general (behavior, "
            "routine, aesthetic, or benefit shift); never a product or single brand."
        ),
    )
    viral_reasons: list[str] = Field(
        default_factory=list,
        description=(
            "1-3 concise one-sentence reasons explaining why the trend looks viral, each grounded "
            "in the provided evidence figures or source alignment."
        ),
    )
    challenge_notes: list[str] = Field(default_factory=list)
    hype_only: bool = False
    seasonal_risk: bool = False


class SynthesizerVerdictBatch(BaseModel):
    verdicts: list[SynthesizerVerdict] = Field(default_factory=list)


class TrendNarrative(BaseModel):
    summary: str
