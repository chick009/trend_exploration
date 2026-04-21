from __future__ import annotations

from app.graph.nodes.lenses import determine_active_lenses


def test_determine_active_lenses_includes_cross_market_diffusion_for_cross_runs() -> None:
    lenses = determine_active_lenses(
        {
            "markets": ["HK", "KR"],
            "analysis_mode": "cross_market",
            "entity_types": ["ingredient", "brand", "function"],
        }
    )
    names = [lens.name for lens in lenses]
    assert "Cross-Market Diffusion" in names
    assert "Brand Breakout" in names


def test_determine_active_lenses_skips_brand_breakout_without_brands() -> None:
    lenses = determine_active_lenses(
        {
            "markets": ["HK"],
            "analysis_mode": "single_market",
            "entity_types": ["ingredient", "function"],
        }
    )
    names = [lens.name for lens in lenses]
    assert "Momentum" in names
    assert "Emerging Ingredient" in names
    assert "Brand Breakout" not in names
    assert "Cross-Market Diffusion" not in names
