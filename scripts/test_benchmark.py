import asyncio
import logging
import sys
import os

# Ensure app is in path
sys.path.append(os.getcwd())

from app.benchmark_collector import BenchmarkCollector

logging.basicConfig(level=logging.INFO)

async def main():
    collector = BenchmarkCollector()
    print("Starting collection test...")
    # Reduce limit for test
    items = await collector.collect_ranking(limit=2)
    print(f"Collected {len(items)} items from ranking.")
    for item in items:
        print(f"Fetching details for {item['name']}...")
        details = await collector.collect_detail(item['product_url'])
        if details:
            print(f"  Got details. HTML len: {len(details.get('detail_html', ''))}, Images: {len(details.get('image_urls', []))}")
            item.update(details)
        await collector.save_product(item)
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
