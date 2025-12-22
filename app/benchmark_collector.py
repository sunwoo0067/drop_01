import logging
import re
# import httpx # Replaced by curl_cffi
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from typing import List, Dict, Any
import asyncio
from datetime import datetime, timezone
from app.models import BenchmarkProduct
from app.db import SessionLocal
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

    async def collect_ranking(self, limit: int = 100, category_url: str | None = None) -> List[Dict[str, Any]]:
        """
        Collects popular products from ranking or search page.
        """
        # Example URL (Digital/Home Appliances)
        url = str(category_url).strip() if category_url else "https://www.coupang.com/np/categories/178255" 
        
        items = []
        # impersonate="chrome" does the magic
        async with AsyncSession(impersonate="chrome", headers=self.headers) as client:
            try:
                response = await client.get(url, allow_redirects=True)
                if response.status_code != 200:
                    logger.error(f"벤치마크 랭킹 페이지 호출 실패: HTTP {response.status_code} ({url})")
                    return []
                
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
                        
                    # Extract Rating and Review Count (Coupang specific)
                    rating_tag = li.select_one("span.rating-star > span.rating")
                    rating = 0.0
                    if rating_tag and "width" in rating_tag.get("style", ""):
                        # style="width: 80%"
                        m_rate = re.search(r"width:\s*(\d+)%", rating_tag["style"])
                        if m_rate:
                            rating = float(m_rate.group(1)) / 20.0 # 100% -> 5.0
                    
                    review_count_tag = li.select_one("span.rating-total-count")
                    review_count = 0
                    if review_count_tag:
                        m_count = re.search(r"(\d+)", review_count_tag.text.replace(",", ""))
                        if m_count:
                            review_count = int(m_count.group(1))

                    items.append({
                        "product_id": product_id,
                        "name": name,
                        "price": price,
                        "product_url": product_url,
                        "vendor_item_id": vendor_item_id,
                        "rating": rating,
                        "review_count": review_count
                    })
                    
            except Exception as e:
                logger.error(f"벤치마크 랭킹 수집 중 오류: {e}")
                return []
                
        return items

    async def collect_detail(self, product_url: str) -> Dict[str, Any]:
        """
        Fetches detail page content:
        """
        async with AsyncSession(impersonate="chrome", headers=self.headers) as client:
            try:
                response = await client.get(product_url, allow_redirects=True)
                if response.status_code != 200:
                    logger.error(f"벤치마크 상세 페이지 호출 실패: HTTP {response.status_code} ({product_url})")
                    return {}

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
                logger.error(f"벤치마크 상세 수집 중 오류: {e}")
                return {}

    async def save_product(self, product_data: Dict[str, Any]):
        """
        Saves product to DB with Embedding.
        """
        raw_data_to_save = dict(product_data)
        raw_data_to_save.pop("detail_html", None)
        raw_data_to_save.pop("image_urls", None)
        raw_html_val = raw_data_to_save.get("raw_html")
        if isinstance(raw_html_val, str) and len(raw_html_val) > 50000:
            raw_data_to_save["raw_html"] = raw_html_val[:50000]

        # New analysis fields
        category_path = product_data.get("category_path")
        review_count = int(product_data.get("review_count", 0))
        rating = float(product_data.get("rating", 0.0))
        quality_score = float(product_data.get("quality_score", 0.0))

        # Generate Embedding
        detail_html_to_save = product_data.get("detail_html")
        if isinstance(detail_html_to_save, str) and len(detail_html_to_save) > 200000:
            detail_html_to_save = detail_html_to_save[:200000]

        detail_html = detail_html_to_save or ""
        detail_text = ""
        try:
            if detail_html:
                detail_text = BeautifulSoup(str(detail_html), "html.parser").get_text(" ", strip=True)
        except Exception:
            detail_text = ""

        image_urls = product_data.get("image_urls") if isinstance(product_data.get("image_urls"), list) else []
        image_hint = " ".join([str(u) for u in image_urls[:10] if u is not None])

        raw_ranking_text = product_data.get("raw_ranking_text") if isinstance(product_data.get("raw_ranking_text"), str) else ""
        raw_ranking_text = raw_ranking_text[:1000]

        text_to_embed = f"{product_data.get('name', '')} {detail_text[:2000]} {raw_ranking_text}".strip()
        embedding = await self.embedding_service.generate_rich_embedding(text_to_embed, image_urls=image_urls)

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
                existing.raw_data = raw_data_to_save
                existing.category_path = category_path
                existing.review_count = review_count
                existing.rating = rating
                existing.quality_score = quality_score
                
                # Update details if available
                if "detail_html" in product_data and (detail_html_to_save or ""):
                    existing.detail_html = detail_html_to_save
                if "image_urls" in product_data and isinstance(product_data.get("image_urls"), list) and product_data.get("image_urls"):
                    existing.image_urls = product_data["image_urls"]
                if embedding:
                    existing.embedding = embedding
                    existing.embedding_updated_at = datetime.now(timezone.utc) if hasattr(existing, 'embedding_updated_at') else None
            else:
                from datetime import timezone
                new_item = BenchmarkProduct(
                    market_code=self.market_code,
                    product_id=str(product_data["product_id"]),
                    name=product_data["name"],
                    price=product_data["price"],
                    product_url=product_data["product_url"],
                    category_path=category_path,
                    review_count=review_count,
                    rating=rating,
                    quality_score=quality_score,
                    detail_html=detail_html_to_save,
                    image_urls=product_data.get("image_urls"),
                    raw_data=raw_data_to_save,
                    embedding=embedding,
                    embedding_updated_at = datetime.now(timezone.utc)
                )
                db.add(new_item)
            
            db.commit()
            logger.info(f"벤치마크 상품 저장 완료: {product_data['name']} (임베딩={'성공' if embedding else '실패'})")

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

    async def run_ranking_collection(self, limit: int = 10, category_url: str | None = None, job_id: Any = None):
        items = await self.collect_ranking(limit=limit, category_url=category_url)
        total = len(items)
        
        from app.models import BenchmarkCollectJob
        
        for idx, item in enumerate(items):
            name = item.get("name") or "(no name)"
            logger.info(f"Processing {name} ({idx+1}/{total})...")
            
            details = await self.collect_detail(str(item.get("product_url") or ""))
            if details:
                item.update(details)
            
            # Simple quality score heuristic: product description length + images
            desc_len = len(item.get("detail_html") or "")
            img_count = len(item.get("image_urls") or [])
            item["quality_score"] = min(10.0, (desc_len / 10000.0) + (img_count * 0.5))
            
            await self.save_product(item)
            
            # Update Job Progress
            if job_id:
                try:
                    with SessionLocal() as db:
                        job = db.get(BenchmarkCollectJob, job_id)
                        if job:
                            job.processed_count = idx + 1
                            job.total_count = total
                            job.progress = int(((idx + 1) / total) * 100) if total > 0 else 100
                            db.commit()
                except Exception as je:
                    logger.error(f"Failed to update job progress: {je}")

            await asyncio.sleep(1)
