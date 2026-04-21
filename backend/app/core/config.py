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
    openrouter_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "OPENAI_API_KEY"),
    )
    openrouter_model: str = Field(
        default="qwen/qwen3.5-35b-a3b",
        validation_alias=AliasChoices("OPENROUTER_MODEL", "OPENAI_MODEL"),
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
