from __future__ import annotations

from typing import Protocol


class BenchmarkCollector(Protocol):
    market_code: str

    async def run_ranking_collection(self, limit: int = 10, category_url: str | None = None):
        ...
