from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.limits import MAX_SOCIAL_POSTS_PER_KEYWORD


Market = Literal["HK", "KR", "TW", "SG", "cross"]
Category = Literal["skincare", "haircare", "makeup", "supplements", "all"]
SourceName = Literal["google_trends", "sales", "tiktok", "instagram"]
AnalysisMode = Literal["single_market", "cross_market"]
RecencySupportStatus = Literal["supported", "partial", "unsupported"]

# Runtime set (not only a type alias) so validation cannot drift from a stale Literal union.
ALLOWED_INGESTION_SOURCES: frozenset[str] = frozenset({"google_trends", "sales", "tiktok", "instagram"})
KEYWORD_DRIVEN_INGESTION_SOURCES: frozenset[str] = frozenset({"google_trends", "tiktok", "instagram"})


class SourceRecencySupport(BaseModel):
    source: SourceName
    status: RecencySupportStatus
    detail: str


class SuggestedKeyword(BaseModel):
    keyword: str = Field(min_length=1, max_length=80)
    rationale: str | None = None


class ExtractionRequestBase(BaseModel):
    market: Market
    category: Category = "all"
    recent_days: int | None = Field(default=7, ge=1, le=30)
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None
    sources: list[str] = Field(
        default_factory=lambda: ["google_trends", "sales"],
        min_length=1,
        description="Data feeds to run: google_trends, sales, tiktok (TikHub photo search), instagram (TikHub hashtag posts).",
        json_schema_extra={
            "items": {"type": "string", "enum": sorted(ALLOWED_INGESTION_SOURCES)},
        },
    )
    max_target_keywords: int = Field(default=5, ge=1, le=20)
    tiktok_photo_count_per_keyword: int | None = Field(
        default=None,
        ge=1,
        le=MAX_SOCIAL_POSTS_PER_KEYWORD,
        description="TikTok photo search page size per approved keyword. Maximum 5 rows are persisted per keyword.",
    )
    instagram_feed_type: Literal["top", "recent"] = Field(
        default="top",
        description="Instagram hashtag feed ordering when ingesting via TikHub.",
    )

    @field_validator("sources", mode="after")
    @classmethod
    def validate_sources(cls, value: list[str]) -> list[str]:
        unknown = [s for s in value if s not in ALLOWED_INGESTION_SOURCES]
        if unknown:
            allowed = ", ".join(sorted(ALLOWED_INGESTION_SOURCES))
            raise ValueError(f"Unknown ingestion source(s): {unknown}. Allowed: {allowed}")
        return value

    @model_validator(mode="after")
    def validate_time_window(self) -> "ExtractionRequestBase":
        if self.from_timestamp and self.to_timestamp and self.from_timestamp > self.to_timestamp:
            raise ValueError("from_timestamp must be earlier than to_timestamp")
        if self.from_timestamp and self.recent_days is not None:
            self.recent_days = None
        return self


class KeywordSuggestionRequest(ExtractionRequestBase):
    pass


class KeywordSuggestionResponse(BaseModel):
    market: Market
    category: Category
    recent_days: int | None = None
    max_target_keywords: int
    sources: list[SourceName]
    suggestions: list[SuggestedKeyword] = Field(default_factory=list)
    guardrail_flags: list[str] = Field(default_factory=list)
    recency_support: list[SourceRecencySupport] = Field(default_factory=list)


class IngestionRunRequest(ExtractionRequestBase):
    target_keywords: list[str] = Field(default_factory=list)
    suggested_keywords: list[str] = Field(default_factory=list)
    seed_terms: list[str] = Field(
        default_factory=list,
        description="Deprecated compatibility field. When target_keywords is empty, seed_terms is copied into target_keywords.",
    )
    max_seed_terms: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Deprecated compatibility field. When provided and max_target_keywords is omitted by older clients, the server reuses the value.",
    )

    @model_validator(mode="after")
    def normalize_keywords(self) -> "IngestionRunRequest":
        if self.max_seed_terms is not None:
            self.max_target_keywords = self.max_seed_terms

        if not self.target_keywords and self.seed_terms:
            self.target_keywords = list(self.seed_terms)

        self.target_keywords = self._normalize_keyword_list(self.target_keywords)
        self.suggested_keywords = self._normalize_keyword_list(self.suggested_keywords)
        if not self.suggested_keywords:
            self.suggested_keywords = list(self.target_keywords)

        if len(self.target_keywords) > 20:
            raise ValueError("target_keywords cannot exceed 20 items")

        keyword_driven_sources = [source for source in self.sources if source in KEYWORD_DRIVEN_INGESTION_SOURCES]
        if keyword_driven_sources and not self.target_keywords:
            joined = ", ".join(keyword_driven_sources)
            raise ValueError(f"target_keywords are required when running keyword-driven sources: {joined}")

        return self

    @staticmethod
    def _normalize_keyword_list(value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            keyword = item.strip()
            if not keyword:
                continue
            key = keyword.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(keyword)
        return normalized


class AnalysisRunRequest(BaseModel):
    market: Market
    category: Category = "all"
    recency_days: int = Field(default=14, ge=1, le=30)
    analysis_mode: AnalysisMode = "single_market"
    query: str | None = Field(
        default=None,
        description="Optional natural-language prompt; converted into SQL-aligned filters before the LangGraph run starts.",
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
    trend_statement: str | None = None
    headline: str
    why_viral: str
    viral_reasons: list[str] = Field(default_factory=list)
    evidence: TrendEvidence
    signal_chips: list[str]
    trend_stage: str
    watch_flag: bool = False
    positivity_score: float | None = None
    lens: str | None = None
    lifecycle_stage: str | None = None
    self_confidence: str | None = None
    challenge_notes: list[str] = Field(default_factory=list)


class LlmUsageSummary(BaseModel):
    llm_call_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    avg_latency_ms: float | None = None
    estimated_cost_usd: float | None = None
    models: list[str] = Field(default_factory=list)


class LlmOpsSummary(BaseModel):
    overall: LlmUsageSummary = Field(default_factory=LlmUsageSummary)
    by_node: dict[str, LlmUsageSummary] = Field(default_factory=dict)


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
    llm_ops: LlmOpsSummary = Field(default_factory=LlmOpsSummary)


class ToolInvocationMessage(BaseModel):
    role: str
    content: str


class ToolInvocation(BaseModel):
    """A single tool call emitted while a LangGraph analysis run executes.

    Tool invocations describe each SQL query against the internal database,
    each LLM call driving planning/scoring, and each memory read/write. The
    frontend consumes this list to render a live tool-use timeline for the
    streaming analysis run.
    """

    id: str
    node: str
    tool: str
    tool_kind: Literal["sql", "llm", "memory"]
    title: str
    status: Literal["running", "success", "error"] = "success"
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None
    input_summary: str | None = None
    sql: str | None = None
    output_summary: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    system_prompt: str | None = None
    user_prompt: str | None = None
    response_text: str | None = None
    messages: list[ToolInvocationMessage] = Field(default_factory=list)


class RunStatusResponse(BaseModel):
    id: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    execution_trace: list[str] = Field(default_factory=list)
    tool_invocations: list[ToolInvocation] = Field(default_factory=list)
    node_outputs: dict[str, Any] = Field(default_factory=dict)
    guardrail_flags: list[str] = Field(default_factory=list)
    target_keywords: list[str] = Field(default_factory=list)
    suggested_keywords: list[str] = Field(default_factory=list)
    recency_support: list[SourceRecencySupport] = Field(default_factory=list)
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
