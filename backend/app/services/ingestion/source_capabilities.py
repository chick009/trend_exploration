from __future__ import annotations

from app.models.schemas import SourceRecencySupport


SOURCE_RECENCY_SUPPORT: dict[str, tuple[str, str]] = {
    "google_trends": (
        "supported",
        "Google Trends derives its query time range from the requested recency window.",
    ),
    "instagram": (
        "partial",
        "Instagram can use a recent-feed ranking, but it does not enforce an exact N-day window.",
    ),
    "tiktok": (
        "unsupported",
        "TikTok photo search does not expose a true recency window in the current integration.",
    ),
    "sales": (
        "unsupported",
        "Sales refresh reloads the local seed table and does not filter extraction by recency.",
    ),
}


def build_recency_support(sources: list[str]) -> list[SourceRecencySupport]:
    support: list[SourceRecencySupport] = []
    for source in sources:
        status, detail = SOURCE_RECENCY_SUPPORT.get(
            source,
            ("unsupported", "This source does not publish recency support metadata."),
        )
        support.append(
            SourceRecencySupport(
                source=source,
                status=status,
                detail=detail,
            )
        )
    return support
