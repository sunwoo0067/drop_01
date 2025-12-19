from __future__ import annotations

from app.benchmark.collectors.base import BenchmarkCollector
from app.benchmark.collectors.auction import AuctionBenchmarkCollector
from app.benchmark.collectors.elevenst import ElevenstBenchmarkCollector
from app.benchmark.collectors.gmarket import GmarketBenchmarkCollector
from app.benchmark.collectors.naver_shopping import NaverShoppingBenchmarkCollector
from app.benchmark_collector import BenchmarkCollector as CoupangBenchmarkCollector


def get_supported_market_codes() -> list[str]:
    return ["COUPANG", "ELEVENST", "GMARKET", "AUCTION", "NAVER_SHOPPING"]


def get_benchmark_collector(market_code: str) -> BenchmarkCollector:
    code = str(market_code or "").strip().upper()
    if code in ("ELEVENST", "11ST", "11STREET"):
        return ElevenstBenchmarkCollector(market_code="ELEVENST")
    if code in ("NAVER_SHOPPING", "NAVER", "NAVERSHOPPING"):
        return NaverShoppingBenchmarkCollector(market_code="NAVER_SHOPPING")
    if code in ("AUCTION",):
        return AuctionBenchmarkCollector(market_code="AUCTION")
    if code in ("GMARKET",):
        return GmarketBenchmarkCollector(market_code="GMARKET")
    return CoupangBenchmarkCollector(market_code="COUPANG")
