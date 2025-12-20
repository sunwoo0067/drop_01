from app.benchmark.collector_factory import get_benchmark_collector
from app.benchmark.collectors.auction import AuctionBenchmarkCollector
from app.benchmark.collectors.elevenst import ElevenstBenchmarkCollector
from app.benchmark.collectors.gmarket import GmarketBenchmarkCollector
from app.benchmark.collectors.naver_shopping import NaverShoppingBenchmarkCollector
from app.benchmark_collector import BenchmarkCollector as CoupangBenchmarkCollector


def test_get_benchmark_collector_returns_expected_types():
    assert isinstance(get_benchmark_collector("coupang"), CoupangBenchmarkCollector)
    assert isinstance(get_benchmark_collector("GMArkeT"), GmarketBenchmarkCollector)
    assert isinstance(get_benchmark_collector("11st"), ElevenstBenchmarkCollector)
    assert isinstance(get_benchmark_collector("naver_Shopping"), NaverShoppingBenchmarkCollector)
    assert isinstance(get_benchmark_collector("auction"), AuctionBenchmarkCollector)
