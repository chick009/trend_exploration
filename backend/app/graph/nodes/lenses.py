from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LensDefinition:
    name: str
    data_keys: tuple[str, ...]
    description: str


LENSES: tuple[LensDefinition, ...] = (
    LensDefinition(
        name="Momentum",
        data_keys=("social", "search"),
        description="Surface fast-rising terms with strong recent velocity.",
    ),
    LensDefinition(
        name="Cross-Market Diffusion",
        data_keys=("social", "search", "sales"),
        description="Compare how the same entity is spreading between markets.",
    ),
    LensDefinition(
        name="Social-Sales Convergence",
        data_keys=("social", "sales"),
        description="Find entities where social attention and commercial activity align.",
    ),
    LensDefinition(
        name="Emerging Ingredient",
        data_keys=("social", "search"),
        description="Find ingredients or functions with low baseline but accelerating growth.",
    ),
    LensDefinition(
        name="Brand Breakout",
        data_keys=("social", "sales"),
        description="Find brands gaining attention disproportionately quickly.",
    ),
)


def determine_active_lenses(intent: dict) -> list[LensDefinition]:
    markets = intent.get("markets", [])
    analysis_mode = intent.get("analysis_mode", "single_market")
    entity_types = set(intent.get("entity_types", []))

    active: list[LensDefinition] = []
    for lens in LENSES:
        if lens.name == "Cross-Market Diffusion" and not (
            analysis_mode == "cross_market" or len(markets) > 1
        ):
            continue
        if lens.name == "Emerging Ingredient" and entity_types and entity_types.isdisjoint({"ingredient", "function"}):
            continue
        if lens.name == "Brand Breakout" and "brand" not in entity_types:
            continue
        active.append(lens)
    return active
