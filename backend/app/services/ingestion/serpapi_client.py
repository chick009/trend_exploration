from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta
from itertools import islice
from typing import Iterable

import httpx

from app.core.config import get_settings


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
        with httpx.Client(timeout=20) as client:
            for terms in chunked(seed_terms, 5):
                params = {
                    "engine": "google_trends",
                    "q": ",".join(terms),
                    "geo": market if market != "cross" else "HK",
                    "date": f"today {max(1, math.ceil(recent_days / 30))}-m",
                    "cat": "44",
                    "data_type": "TIMESERIES",
                    "api_key": self.settings.serpapi_api_key,
                }
                response = client.get("https://serpapi.com/search.json", params=params)
                response.raise_for_status()
                payload = response.json()
                timeline = payload.get("interest_over_time", {}).get("timeline_data", [])
                for index, term in enumerate(terms):
                    values = []
                    for point in timeline:
                        extracted = point.get("values", [])
                        if index < len(extracted):
                            values.append(extracted[index].get("extracted_value", 0))
                    wow_delta = compute_wow_delta(values)
                    rows.append(
                        {
                            "keyword": term,
                            "geo": params["geo"],
                            "snapshot_date": date.today().isoformat(),
                            "index_value": values[-1] if values else 0,
                            "wow_delta": wow_delta,
                            "is_breakout": wow_delta > 0.25,
                            "related_rising": [],
                            "raw_timeseries": values,
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
