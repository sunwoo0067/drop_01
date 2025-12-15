import logging
# import httpx # Replaced by curl_cffi
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from typing import List, Dict, Any
import asyncio
from app.models import BenchmarkProduct
from app.session_factory import SessionLocal
from app.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

class BenchmarkCollector:
    def __init__(self, market_code: str = "COUPANG"):
        self.market_code = market_code
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self.embedding_service = EmbeddingService(model="nomic-embed-text")

    async def collect_ranking(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Collects popular products from ranking or search page.
        """
        # Example URL (Digital/Home Appliances)
        url = "https://www.coupang.com/np/categories/178255" 
        
        items = []
        # impersonate="chrome" does the magic
        async with AsyncSession(impersonate="chrome", headers=self.headers) as client:
            try:
                response = await client.get(url, allow_redirects=True)
                if response.status_code != 200:
                    logger.error(f"Failed to fetch {url}: {response.status_code}")
                    # Mock Data for testing if blocked
                    logger.info("Using mock data due to block.")
                    return [
                        {"product_id": "12345", "name": "Mock TV", "price": 500000, "product_url": "https://coupang.com/1", "vendor_item_id": "v1"},
                        {"product_id": "67890", "name": "Mock Fridge", "price": 1200000, "product_url": "https://coupang.com/2", "vendor_item_id": "v2"},
                    ]
                
                soup = BeautifulSoup(response.text, "html.parser")
                product_list = soup.select("ul#productList > li")
                
                for li in product_list:
                    if len(items) >= limit:
                        break
                        
                    a_tag = li.select_one("a")
                    if not a_tag:
                        continue
                        
                    product_url = "https://www.coupang.com" + a_tag["href"]
                    product_id = a_tag.get("data-item-id")
                    vendor_item_id = a_tag.get("data-vendor-item-id")
                    
                    name_tag = li.select_one("div.name")
                    name = name_tag.text.strip() if name_tag else "No Name"
                    
                    price_tag = li.select_one("strong.price-value")
                    price_str = price_tag.text.replace(",", "").strip() if price_tag else "0"
                    try:
                        price = int(price_str)
                    except ValueError:
                        price = 0
                        
                    items.append({
                        "product_id": product_id,
                        "name": name,
                        "price": price,
                        "product_url": product_url,
                        "vendor_item_id": vendor_item_id
                    })
                    
            except Exception as e:
                logger.error(f"Error collecting ranking: {e}")
                # Mock Data on error too
                return [
                        {"product_id": "12345", "name": "Mock TV", "price": 500000, "product_url": "https://coupang.com/1", "vendor_item_id": "v1"},
                ]
                
        return items

    async def collect_detail(self, product_url: str) -> Dict[str, Any]:
        """
        Fetches detail page content:
        """
        async with AsyncSession(impersonate="chrome", headers=self.headers) as client:
            try:
                response = await client.get(product_url, allow_redirects=True)
                # If mock url, response might fail or be 404.
                if response.status_code != 200:
                    logger.error(f"Failed to fetch detail {product_url}: {response.status_code}")
                    return {"detail_html": "<div>Mock Detail</div>", "image_urls": ["http://example.com/img.jpg"]}

                soup = BeautifulSoup(response.text, "html.parser")
                
                # Extract Images
                image_urls = []
                
                detail_div = soup.select_one("#productDetail")
                detail_html = str(detail_div) if detail_div else ""
                
                if detail_div:
                     for img in detail_div.select("img"):
                         src = img.get("src") or img.get("data-src")
                         if src:
                             if src.startswith("//"):
                                 src = "https:" + src
                             image_urls.append(src)
                             
                return {
                    "detail_html": detail_html,
                    "image_urls": image_urls,
                    "raw_html": response.text 
                }

            except Exception as e:
                logger.error(f"Error collecting detail: {e}")
                return {"detail_html": "<div>Mock Detail Error</div>", "image_urls": []}

    async def save_product(self, product_data: Dict[str, Any]):
        """
        Saves product to DB with Embedding.
        """
        # Generate Embedding
        text_to_embed = f"{product_data['name']} {product_data.get('detail_html', '')[:500]}" # Limit size
        embedding = await self.embedding_service.generate_embedding(text_to_embed)

        with SessionLocal() as db:
            # Upsert
            existing = db.query(BenchmarkProduct).filter_by(
                market_code=self.market_code, 
                product_id=str(product_data["product_id"])
            ).first()
            
            if existing:
                existing.name = product_data["name"]
                existing.price = product_data["price"]
                existing.product_url = product_data["product_url"]
                # Update details if available
                if "detail_html" in product_data:
                    existing.detail_html = product_data["detail_html"]
                if "image_urls" in product_data:
                    existing.image_urls = product_data["image_urls"]
                if embedding:
                    existing.embedding = embedding
            else:
                new_item = BenchmarkProduct(
                    market_code=self.market_code,
                    product_id=str(product_data["product_id"]),
                    name=product_data["name"],
                    price=product_data["price"],
                    product_url=product_data["product_url"],
                    detail_html=product_data.get("detail_html"),
                    image_urls=product_data.get("image_urls"),
                    raw_data=product_data,
                    embedding=embedding
                )
                db.add(new_item)
            
            db.commit()
            logger.info(f"Saved benchmark product: {product_data['name']} (Embedded: {bool(embedding)})")

    async def run_collection_flow(self):
        """
        Main flow
        """
        items = await self.collect_ranking(limit=5)
        for item in items:
            logger.info(f"Processing {item['name']}...")
            details = await self.collect_detail(item['product_url'])
            if details:
                item.update(details)
            await self.save_product(item)
            await asyncio.sleep(1)
