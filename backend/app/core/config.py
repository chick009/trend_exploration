from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Health & Beauty Trend Discovery API"
    environment: str = "development"
    enable_scheduler: bool = False

    project_root: Path = Path(__file__).resolve().parents[2]
    database_path: Path = Field(default=Path(__file__).resolve().parents[2] / "trend_mvp.sqlite")

    serpapi_api_key: str | None = None
    tikhub_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TIKHUB_API_KEY", "REDNOTE_API_KEY"),
    )
    tikhub_cookie: str | None = Field(default=None, validation_alias=AliasChoices("TIKHUB_COOKIE"))
    openrouter_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "OPENAI_API_KEY"),
    )
    openrouter_model: str = Field(
        default="qwen/qwen3.5-35b-a3b",
        validation_alias=AliasChoices("OPENROUTER_MODEL", "OPENAI_MODEL"),
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    cors_origins: str = ""
    cors_origin_regex: str | None = r"https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    cors_allow_credentials: bool = False

    default_markets: list[str] = Field(default_factory=lambda: ["HK", "KR", "TW", "SG"])
    default_seed_terms: list[str] = Field(
        default_factory=lambda: [
            "niacinamide",
            "tranexamic acid",
            "ceramide",
            "retinol",
            "snail mucin",
            "cica",
            "bakuchiol",
            "glass skin",
            "skin barrier repair",
            "double cleanse",
        ]
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    def parsed_cors_origins(self) -> list[str]:
        if isinstance(self.cors_origins, list):
            return [str(origin).strip() for origin in self.cors_origins if str(origin).strip()]
        raw = str(self.cors_origins or "").strip()
        if not raw:
            return []
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
