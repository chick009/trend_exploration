from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.core.config import get_settings


def get_chat_model(*, temperature: float = 0.0, model: str | None = None) -> ChatOpenAI:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY is required for LangGraph analysis nodes.")

    return ChatOpenAI(
        model=model or settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=temperature,
        default_headers={
            "HTTP-Referer": "http://localhost",
            "X-Title": "trend-exploration-mvp",
        },
    )
