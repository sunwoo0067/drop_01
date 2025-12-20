from __future__ import annotations

from typing import Protocol, Any


class BenchmarkCollector(Protocol):
    market_code: str

    async def run_ranking_collection(self, limit: int = 10, category_url: str | None = None, job_id: Any = None):
        ...
