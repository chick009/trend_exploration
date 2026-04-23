from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any, TypeVar, TypedDict

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core.config import get_settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LlmTrace(TypedDict):
    system_prompt: str
    user_prompt: str
    response_text: str | None
    model: str
    duration_ms: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None


class JsonResponseError(ValueError):
    def __init__(self, message: str, *, trace: LlmTrace) -> None:
        super().__init__(message)
        self.trace = trace


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


def _resolved_model_name(model: str | None) -> str:
    settings = get_settings()
    return model or settings.openrouter_model


def _extract_usage_int(usage_sources: list[dict[str, Any]], *keys: str) -> int | None:
    for source in usage_sources:
        for key in keys:
            value = source.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                return int(value)
    return None


def _extract_usage_float(metadata_sources: list[dict[str, Any]], *keys: str) -> float | None:
    for source in metadata_sources:
        for key in keys:
            value = source.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                return round(float(value), 8)
    return None


def _extract_response_observability(response: Any, *, fallback_model: str) -> dict[str, Any]:
    response_metadata = getattr(response, "response_metadata", None)
    response_metadata = response_metadata if isinstance(response_metadata, dict) else {}
    usage_metadata = getattr(response, "usage_metadata", None)
    usage_sources: list[dict[str, Any]] = []
    metadata_sources: list[dict[str, Any]] = [response_metadata]
    if isinstance(usage_metadata, dict):
        usage_sources.append(usage_metadata)
        metadata_sources.append(usage_metadata)
    for key in ("token_usage", "usage", "usage_metadata"):
        candidate = response_metadata.get(key)
        if isinstance(candidate, dict):
            usage_sources.append(candidate)
            metadata_sources.append(candidate)

    prompt_tokens = _extract_usage_int(usage_sources, "input_tokens", "prompt_tokens")
    completion_tokens = _extract_usage_int(usage_sources, "output_tokens", "completion_tokens")
    total_tokens = _extract_usage_int(usage_sources, "total_tokens")
    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens

    model_name = str(
        response_metadata.get("model_name")
        or response_metadata.get("model")
        or fallback_model
    )
    estimated_cost_usd = _extract_usage_float(
        metadata_sources,
        "cost",
        "total_cost",
        "estimated_cost",
        "estimated_cost_usd",
    )
    return {
        "model": model_name,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": estimated_cost_usd,
    }


def _invoke_json_response_internal(
    schema: type[SchemaT],
    *,
    user_prompt: str,
    system_prompt: str,
    model: str | None = None,
) -> tuple[SchemaT, LlmTrace]:
    schema_json = json.dumps(schema.model_json_schema(), indent=2, sort_keys=True)
    resolved_model = _resolved_model_name(model)
    trace: LlmTrace = {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "response_text": None,
        "model": resolved_model,
        "duration_ms": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "estimated_cost_usd": None,
    }
    started_at = perf_counter()
    try:
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
    except Exception as exc:
        trace["duration_ms"] = round((perf_counter() - started_at) * 1000, 2)
        raise JsonResponseError(f"Model invocation failed for {schema.__name__}: {exc!s}", trace=trace) from exc

    trace["duration_ms"] = round((perf_counter() - started_at) * 1000, 2)
    trace.update(_extract_response_observability(response, fallback_model=resolved_model))
    content = getattr(response, "content", response)
    if isinstance(content, dict):
        trace["response_text"] = json.dumps(content, default=str)
        return schema.model_validate(content), trace

    text = _content_to_text(content)
    trace["response_text"] = text

    last_error: Exception | None = None
    for candidate in _iter_json_candidates(text):
        try:
            return schema.model_validate_json(candidate), trace
        except Exception as exc:  # pragma: no cover - only used on malformed model replies
            last_error = exc

    preview = text[:500] + ("..." if len(text) > 500 else "")
    raise JsonResponseError(
        (
            f"Model did not return valid JSON for {schema.__name__}. "
            f"Last parse error: {last_error!s}. Response preview: {preview}"
        ),
        trace=trace,
    )


def invoke_json_response_with_trace(
    schema: type[SchemaT],
    *,
    user_prompt: str,
    system_prompt: str,
    model: str | None = None,
) -> tuple[SchemaT, LlmTrace]:
    return _invoke_json_response_internal(
        schema,
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        model=model,
    )


def invoke_json_response(
    schema: type[SchemaT],
    *,
    user_prompt: str,
    system_prompt: str,
    model: str | None = None,
) -> SchemaT:
    response, _trace = invoke_json_response_with_trace(
        schema,
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        model=model,
    )
    return response
