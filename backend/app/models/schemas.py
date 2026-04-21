from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


Market = Literal["HK", "KR", "TW", "SG", "cross"]
Category = Literal["skincare", "haircare", "makeup", "supplements", "all"]
SourceName = Literal["rednote", "google_trends", "sales", "tiktok", "instagram"]
AnalysisMode = Literal["single_market", "cross_market"]

# Runtime set (not only a type alias) so validation cannot drift from a stale Literal union.
ALLOWED_INGESTION_SOURCES: frozenset[str] = frozenset({"rednote", "google_trends", "sales", "tiktok", "instagram"})


class IngestionRunRequest(BaseModel):
    market: Market
    category: Category = "all"
    recent_days: int | None = Field(default=7, ge=1, le=30)
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None
    sources: list[str] = Field(
        default_factory=lambda: ["rednote", "google_trends", "sales"],
        min_length=1,
        description="Data feeds to run: rednote, google_trends, sales, tiktok (TikHub photo search), instagram (TikHub hashtag posts).",
        json_schema_extra={
            "items": {"type": "string", "enum": sorted(ALLOWED_INGESTION_SOURCES)},
        },
    )
    seed_terms: list[str] = Field(default_factory=list)
    max_seed_terms: int = Field(default=5, ge=1, le=20)
    max_notes_per_keyword: int = Field(default=5, ge=1, le=20)
    max_comment_posts_per_keyword: int = Field(default=2, ge=0, le=10)
    max_comments_per_post: int = Field(default=5, ge=1, le=20)

    @field_validator("sources", mode="after")
    @classmethod
    def validate_sources(cls, value: list[str]) -> list[str]:
        unknown = [s for s in value if s not in ALLOWED_INGESTION_SOURCES]
        if unknown:
            allowed = ", ".join(sorted(ALLOWED_INGESTION_SOURCES))
            raise ValueError(f"Unknown ingestion source(s): {unknown}. Allowed: {allowed}")
        return value

    @model_validator(mode="after")
    def validate_time_window(self) -> "IngestionRunRequest":
        if self.from_timestamp and self.to_timestamp and self.from_timestamp > self.to_timestamp:
            raise ValueError("from_timestamp must be earlier than to_timestamp")
        if self.from_timestamp and self.recent_days is not None:
            self.recent_days = None
        if self.max_comment_posts_per_keyword > self.max_notes_per_keyword:
            self.max_comment_posts_per_keyword = self.max_notes_per_keyword
        return self


class AnalysisRunRequest(BaseModel):
    market: Market
    category: Category = "all"
    recency_days: int = Field(default=14, ge=1, le=30)
    analysis_mode: AnalysisMode = "single_market"
    query: str | None = Field(
        default=None,
        description="Optional natural-language prompt; echoed in the graph trace for transparency.",
    )


class TrendEvidence(BaseModel):
    social: str | None = None
    search: str | None = None
    sales: str | None = None
    cross_market: str | None = None


class TrendCard(BaseModel):
    rank: int
    term: str
    entity_type: str
    virality_score: float
    confidence_tier: str
    headline: str
    why_viral: str
    evidence: TrendEvidence
    signal_chips: list[str]
    trend_stage: str
    watch_flag: bool = False
    positivity_score: float | None = None
    lens: str | None = None
    lifecycle_stage: str | None = None
    self_confidence: str | None = None
    challenge_notes: list[str] = Field(default_factory=list)


class TrendReport(BaseModel):
    report_id: str
    generated_at: datetime
    market: str
    category: str
    recency_days: int
    trends: list[TrendCard]
    watch_list: list[TrendCard] = Field(default_factory=list)
    regional_divergences: list[dict[str, Any]] = Field(default_factory=list)
    execution_trace: list[str] = Field(default_factory=list)
    guardrail_flags: list[str] = Field(default_factory=list)


class RunStatusResponse(BaseModel):
    id: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    execution_trace: list[str] = Field(default_factory=list)
    guardrail_flags: list[str] = Field(default_factory=list)
    source_batch_id: str | None = None
    report: TrendReport | None = None


class PaginatedRunsResponse(BaseModel):
    items: list[RunStatusResponse]
    total: int
    limit: int
    offset: int


class SourceHealth(BaseModel):
    source: str
    latest_batch_id: str | None
    latest_completed_at: datetime | None
    row_count: int


class SourcesHealthResponse(BaseModel):
    sources: list[SourceHealth]


class DbTableInfo(BaseModel):
    name: str
    description: str
    row_count: int
    last_updated: datetime | None = None


class DbTablesResponse(BaseModel):
    tables: list[DbTableInfo]


class DbColumnSchema(BaseModel):
    name: str
    data_type: str
    nullable: bool
    is_primary_key: bool
    is_indexed: bool


class DbTableSchemaResponse(BaseModel):
    table: str
    columns: list[DbColumnSchema]


class DbTableRowsResponse(BaseModel):
    table: str
    columns: list[str]
    rows: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
