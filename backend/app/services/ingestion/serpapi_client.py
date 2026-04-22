from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta
from itertools import islice
from typing import Any, Iterable

import httpx

from app.core.config import get_settings

REQUEST_TIMEOUT_SECONDS = 45
MAX_RETRIES = 3
MARKET_TZ_MAP = {
    "HK": "-480",
    "KR": "-540",
    "TW": "-480",
    "SG": "-480",
}


def chunked(iterable: Iterable[str], size: int) -> Iterable[list[str]]:
    iterator = iter(iterable)
    while batch := list(islice(iterator, size)):
        yield batch


def compute_wow_delta(values: list[float]) -> float:
    if len(values) < 14:
        return 0.0
    this_week = sum(values[-7:]) / 7
    last_week = sum(values[-14:-7]) / 7
    return (this_week - last_week) / (last_week + 1e-9)


class SerpApiClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _build_date_param(self, recent_days: int) -> str:
        if recent_days <= 1:
            return "now 1-d"
        if recent_days == 7:
            return "now 7-d"
        if recent_days == 30:
            return "today 1-m"
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=max(recent_days - 1, 0))
        return f"{start_date.isoformat()} {end_date.isoformat()}"

    def _build_tz_param(self, market: str) -> str:
        return MARKET_TZ_MAP.get(market, "420")

    def _build_geo_param(self, market: str) -> str:
        return market if market != "cross" else "HK"

    def _request_json(self, client: httpx.Client, *, params: dict[str, Any]) -> dict[str, Any]:
        last_exception: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = client.get("https://serpapi.com/search", params=params)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise RuntimeError("SerpAPI returned a non-JSON Google Trends payload")
                metadata = payload.get("search_metadata") or {}
                status = metadata.get("status")
                if status not in (None, "", "Success"):
                    error_message = payload.get("error") or f"SerpAPI Google Trends search returned status: {status}"
                    raise RuntimeError(str(error_message))
                return payload
            except (httpx.TimeoutException, httpx.RequestError, RuntimeError) as exc:
                last_exception = exc
                if attempt == MAX_RETRIES:
                    raise
        if last_exception is not None:
            raise last_exception
        raise RuntimeError("SerpAPI Google Trends request failed without an error")

    def _extract_series_points(
        self,
        *,
        term: str,
        index: int,
        timeline: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        series: list[dict[str, Any]] = []
        normalized_term = term.casefold()
        for point in timeline:
            if not isinstance(point, dict):
                continue
            values = point.get("values")
            if not isinstance(values, list) or not values:
                continue
            value_entry: dict[str, Any] | None = None
            for candidate in values:
                if isinstance(candidate, dict) and str(candidate.get("query") or "").casefold() == normalized_term:
                    value_entry = candidate
                    break
            if value_entry is None and index < len(values) and isinstance(values[index], dict):
                value_entry = values[index]
            if value_entry is None:
                continue
            extracted_value = value_entry.get("extracted_value", 0)
            try:
                numeric_value = float(extracted_value)
            except (TypeError, ValueError):
                numeric_value = 0.0
            series.append(
                {
                    "date": point.get("date"),
                    "timestamp": point.get("timestamp"),
                    "query": value_entry.get("query") or term,
                    "value": value_entry.get("value"),
                    "extracted_value": numeric_value,
                }
            )
        return series

    def fetch_trends(
        self,
        *,
        market: str,
        category: str,
        recent_days: int,
        seed_terms: list[str],
    ) -> list[dict]:
        if not self.settings.serpapi_api_key:
            return self._synthetic_trends(market=market, category=category, recent_days=recent_days, seed_terms=seed_terms)

        rows: list[dict] = []
        date_param = self._build_date_param(recent_days)
        geo = self._build_geo_param(market)
        tz = self._build_tz_param(market)
        with httpx.Client(timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=10.0)) as client:
            for terms in chunked(seed_terms, 5):
                params = {
                    "engine": "google_trends",
                    "q": ",".join(terms),
                    "geo": geo,
                    "hl": "en",
                    "date": date_param,
                    "tz": tz,
                    "cat": "44",
                    "data_type": "TIMESERIES",
                    "api_key": self.settings.serpapi_api_key,
                }
                payload = self._request_json(client, params=params)
                timeline = payload.get("interest_over_time", {}).get("timeline_data", [])
                for index, term in enumerate(terms):
                    series = self._extract_series_points(term=term, index=index, timeline=timeline if isinstance(timeline, list) else [])
                    values = [float(point.get("extracted_value", 0) or 0) for point in series]
                    wow_delta = compute_wow_delta(values)
                    rows.append(
                        {
                            "keyword": term,
                            "geo": geo,
                            "snapshot_date": date.today().isoformat(),
                            "index_value": values[-1] if values else 0,
                            "wow_delta": wow_delta,
                            "is_breakout": wow_delta > 0.25,
                            "related_rising": [],
                            "raw_timeseries": series,
                            "source": "serpapi",
                        }
                    )
        return rows

    def _synthetic_trends(
        self,
        *,
        market: str,
        category: str,
        recent_days: int,
        seed_terms: list[str],
    ) -> list[dict]:
        rows: list[dict] = []
        today = datetime.utcnow().date()
        for term in seed_terms:
            randomizer = random.Random(f"{market}:{category}:{term}:{recent_days}")
            baseline = randomizer.randint(18, 48)
            momentum = randomizer.uniform(0.05, 0.55)
            if market == "HK" and term in {"tranexamic acid", "glass skin"}:
                momentum += 0.2
            if market == "KR" and term in {"bakuchiol", "cica"}:
                momentum += 0.16
            if market == "TW" and term in {"niacinamide", "SPF serum"}:
                momentum += 0.12
            values = []
            current = float(baseline)
            for _ in range(max(14, recent_days)):
                current = max(5.0, current * (1 + randomizer.uniform(-0.05, momentum / 4)))
                values.append(round(current, 2))
            wow_delta = compute_wow_delta(values)
            rows.append(
                {
                    "keyword": term,
                    "geo": market if market != "cross" else "HK",
                    "snapshot_date": today.isoformat(),
                    "index_value": round(values[-1], 2),
                    "wow_delta": wow_delta,
                    "is_breakout": wow_delta > 0.2,
                    "related_rising": [f"{term} serum", f"{term} review", f"{term} before after"],
                    "raw_timeseries": values[-recent_days:],
                    "source": "synthetic_serpapi",
                }
            )
        return rows
