from __future__ import annotations

import json
import random
from datetime import date, timedelta

from app.db.connection import connection_scope
from app.seed.reference_data import ENTITY_SEEDS, SALES_SKU_SEEDS


def seed_reference_data() -> None:
    with connection_scope() as connection:
        for entity in ENTITY_SEEDS:
            connection.execute(
                """
                INSERT OR REPLACE INTO entity_dictionary (
                    canonical_term,
                    aliases,
                    entity_type,
                    hb_category,
                    origin_market,
                    description
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entity["canonical_term"],
                    json.dumps(entity["aliases"]),
                    entity["entity_type"],
                    entity["hb_category"],
                    entity["origin_market"],
                    entity["description"],
                ),
            )


def seed_sales_data() -> None:
    randomizer = random.Random(11)
    weeks = [date.today() - timedelta(days=7 * offset) for offset in range(8, -1, -1)]
    regions = ["HK", "KR", "TW", "SG"]
    with connection_scope() as connection:
        for base in SALES_SKU_SEEDS:
            for region in regions:
                running_units = randomizer.randint(45, 120)
                for week in weeks:
                    growth = randomizer.uniform(-0.08, 0.42)
                    if region == "HK" and "tranexamic acid" in base["ingredient_tags"]:
                        growth += 0.25
                    if region == "KR" and "bakuchiol" in base["ingredient_tags"]:
                        growth += 0.15
                    next_units = max(20, int(running_units * (1 + growth)))
                    wow_velocity = (next_units - running_units) / max(running_units, 1)
                    restocking = 1 if wow_velocity > 0.25 else 0
                    revenue = round(next_units * randomizer.uniform(12, 32), 2)
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO sales_data (
                            sku,
                            product_name,
                            brand,
                            ingredient_tags,
                            category,
                            region,
                            week_start,
                            units_sold,
                            revenue,
                            wow_velocity,
                            is_restocking,
                            source_batch_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"{base['sku']}-{region}",
                            base["product_name"],
                            base["brand"],
                            json.dumps(base["ingredient_tags"]),
                            base["category"],
                            region,
                            week.isoformat(),
                            next_units,
                            revenue,
                            wow_velocity,
                            restocking,
                            "synthetic_sales_seed",
                        ),
                    )
                    running_units = next_units
