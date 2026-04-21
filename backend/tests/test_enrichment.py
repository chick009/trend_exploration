from __future__ import annotations

from app.db.bootstrap import seed_reference_data
from app.db.migrator import apply_migrations
from app.services.ingestion.llm_enrichment import LLMEnrichmentService


def test_enrichment_extracts_entities_and_sentiment(test_database) -> None:
    apply_migrations()
    seed_reference_data()
    service = LLMEnrichmentService()

    result = service.enrich_text(
        text="I love this niacinamide serum for glass skin. The finish is glowy and gentle.",
        category_hint="skincare",
    )

    assert result.llm_category == "skincare"
    assert "niacinamide" in result.llm_entities
    assert result.positivity_score > 0.5
    assert result.relevance_score >= 0.55
