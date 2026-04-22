from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core.config import get_settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def get_chat_model(*, model: str | None = None) -> ChatOpenAI:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY is required for LangGraph analysis nodes.")

    return ChatOpenAI(
        model=model or settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                parts.append(str(text if text is not None else json.dumps(item, default=str)))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    if isinstance(content, dict):
        return json.dumps(content, default=str)
    return str(content)


def _iter_json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    stripped = text.strip()
    if stripped:
        candidates.append(stripped)

    fenced = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    candidates.extend(match.strip() for match in fenced if match.strip())

    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1].strip()
            if candidate:
                candidates.append(candidate)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            deduped.append(candidate)
    return deduped


def invoke_json_response(
    schema: type[SchemaT],
    *,
    user_prompt: str,
    system_prompt: str,
    model: str | None = None,
) -> SchemaT:
    schema_json = json.dumps(schema.model_json_schema(), indent=2, sort_keys=True)
    response = get_chat_model(model=model).invoke(
        [
            (
                "system",
                f"{system_prompt}\n"
                f"Schema name: {schema.__name__}\n"
                "Return only valid JSON that matches the schema exactly.\n"
                "Do not include markdown fences or commentary.\n"
                f"JSON schema:\n{schema_json}",
            ),
            ("human", user_prompt),
        ]
    )
    content = getattr(response, "content", response)
    if isinstance(content, dict):
        return schema.model_validate(content)

    last_error: Exception | None = None
    text = _content_to_text(content)
    for candidate in _iter_json_candidates(text):
        try:
            return schema.model_validate_json(candidate)
        except Exception as exc:  # pragma: no cover - only used on malformed model replies
            last_error = exc

    preview = text[:500] + ("..." if len(text) > 500 else "")
    raise ValueError(
        f"Model did not return valid JSON for {schema.__name__}. "
        f"Last parse error: {last_error!s}. Response preview: {preview}"
    )
