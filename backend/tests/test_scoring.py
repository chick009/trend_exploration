from __future__ import annotations

from app.graph.graph import confidence_gate
from app.graph.nodes.synthesizer import assign_confidence, determine_lifecycle_stage, normalize_score


def test_normalize_score_handles_flat_ranges() -> None:
    assert normalize_score(0.5, 0.5, 0.5) == 0.5
    assert normalize_score(0.0, 0.0, 0.0) == 0.0


def test_assign_confidence_uses_sources_and_score() -> None:
    assert assign_confidence(3, 0.7) == "high"
    assert assign_confidence(2, 0.5) == "medium"
    assert assign_confidence(1, 0.8) == "low"


def test_determine_lifecycle_stage_uses_prior_score() -> None:
    assert determine_lifecycle_stage(0.45, None) == "emerging"
    assert determine_lifecycle_stage(0.8, 0.6) == "accelerating"
    assert determine_lifecycle_stage(0.79, 0.77) == "peak"
    assert determine_lifecycle_stage(0.5, 0.7) == "declining"


def test_confidence_gate_has_three_paths() -> None:
    assert confidence_gate({"synthesized_trends": []}) == "insufficient_data"
    assert confidence_gate({"synthesized_trends": [{"status": "confirmed"}], "watch_list_only": True}) == "low_signal"
    assert (
        confidence_gate(
            {
                "synthesized_trends": [
                    {"status": "confirmed"},
                    {"status": "confirmed"},
                    {"status": "confirmed"},
                ]
            }
        )
        == "proceed"
    )
