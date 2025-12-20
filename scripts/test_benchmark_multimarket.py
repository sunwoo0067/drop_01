import asyncio
import logging
from app.benchmark.collector_factory import get_benchmark_collector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_all_markets():
    markets = ["NAVER_SHOPPING", "GMARKET", "ELEVENST"]
    
    for market in markets:
        logger.info(f"--- Testing {market} ---")
        try:
            collector = get_benchmark_collector(market)
            items = await collector.collect_ranking(limit=3)
            logger.info(f"Collected {len(items)} items from {market}")
            for item in items:
                logger.info(f"- {item.get('name')} : {item.get('price')} KRW")
                if item.get('product_url'):
                    details = await collector.collect_detail(item['product_url'])
                    logger.info(f"  > Detail HTML len: {len(details.get('detail_html', ''))}")
        except Exception as e:
            logger.error(f"Failed to collect from {market}: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_all_markets())
