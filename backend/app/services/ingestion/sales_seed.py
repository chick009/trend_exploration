from __future__ import annotations

from app.db.bootstrap import seed_sales_data


class SalesSeedService:
    def refresh(self) -> dict[str, int]:
        seed_sales_data()
        return {"rows_seeded": 216}
