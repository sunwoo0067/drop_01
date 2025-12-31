import logging
import re
# import httpx # Replaced by curl_cffi
from curl_cffi.requests import AsyncSession
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Tuple
import asyncio
from datetime import datetime, timezone
from app.models import BenchmarkProduct
from app.db import SessionLocal
from app.embedding_service import EmbeddingService
from app.settings import settings


logger = logging.getLogger(__name__)

class BenchmarkCollector:
    def __init__(self, market_code: str = "COUPANG"):
        self.market_code = market_code
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self.embedding_service = EmbeddingService(model="nomic-embed-text")

    async def _fetch_via_proxy(self, url: str) -> Tuple[int, str]:
        """
        Fetches content via Supabase Edge Function proxy.
        """
        sef_url = f"{settings.supabase_url}/functions/v1/fetch-proxy"
        sef_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.supabase_service_role_key}"
        }
        
        payload = {
            "method": "GET",
            "url": url,
            "headers": self.headers
        }
        
        timeout = httpx.Timeout(300.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(sef_url, json=payload, headers=sef_headers)
                resp.raise_for_status()
                data = resp.json()
                return data.get("status", 500), data.get("data", "")
            except Exception as e:
                logger.error(f"Proxy fetch failed for {url}: {e}")
                return 500, ""

    async def collect_ranking(self, limit: int = 100, category_url: str | None = None) -> List[Dict[str, Any]]:
        """
        Collects popular products from ranking or search page.
        """
        url = str(category_url).strip() if category_url else "https://www.coupang.com/np/categories/178255" 
        
        items = []
        html_content = ""
        
        if settings.ownerclan_use_self_proxy:
            status, html_content = await self._fetch_via_proxy(url)
            if status != 200:
                logger.error(f"벤치마크 랭킹 페이지 호출 실패 (Proxy): HTTP {status} ({url})")
                return []
        else:
            async with AsyncSession(impersonate="chrome", headers=self.headers) as client:
                try:
                    response = await client.get(url, allow_redirects=True)
                    if response.status_code != 200:
                        logger.error(f"벤치마크 랭킹 페이지 호출 실패: HTTP {response.status_code} ({url})")
                        return []
                    html_content = response.text
                except Exception as e:
                    logger.error(f"벤치마크 랭킹 수집 중 오류: {e}")
                    return []
        
        try:
            soup = BeautifulSoup(html_content, "html.parser")
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
                    
                # Extract Rating and Review Count
                rating_tag = li.select_one("span.rating-star > span.rating")
                rating = 0.0
                if rating_tag and "width" in rating_tag.get("style", ""):
                    m_rate = re.search(r"width:\s*(\d+)%", rating_tag["style"])
                    if m_rate:
                        rating = float(m_rate.group(1)) / 20.0
                
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
                    "review_count": review_count,
                    "market": "COUPANG"
                })
        except Exception as e:
            logger.error(f"벤치마크 랭킹 파싱 중 오류: {e}")
            return []
            
        return items

    async def collect_detail(self, product_url: str) -> Dict[str, Any]:
        """
        Fetches detail page content.
        """
        html_content = ""
        if settings.ownerclan_use_self_proxy:
            status, html_content = await self._fetch_via_proxy(product_url)
            if status != 200:
                logger.error(f"벤치마크 상세 페이지 호출 실패 (Proxy): HTTP {status} ({product_url})")
                return {}
        else:
            async with AsyncSession(impersonate="chrome", headers=self.headers) as client:
                try:
                    response = await client.get(product_url, allow_redirects=True)
                    if response.status_code != 200:
                        logger.error(f"벤치마크 상세 페이지 호출 실패: HTTP {response.status_code} ({product_url})")
                        return {}
                    html_content = response.text
                except Exception as e:
                    logger.error(f"벤치마크 상세 수집 중 오류: {e}")
                    return {}

        try:
            soup = BeautifulSoup(html_content, "html.parser")
            
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
                "raw_html": html_content
            }
        except Exception as e:
            logger.error(f"벤치마크 상세 파싱 중 오류: {e}")
            return {}


    async def save_product(self, product_data: Dict[str, Any]):
        """
        Saves product to DB with Embedding.
        """
        raw_data_to_save = dict(product_data)
        raw_data_to_save.pop("detail_html", None)
        raw_data_to_save.pop("image_urls", None)
        # Keep reviews if they exist
        reviews = product_data.get("reviews")
        if reviews:
            raw_data_to_save["reviews"] = reviews
        
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
        
        saved_id = None
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
            saved_id = existing.id if existing else new_item.id
            logger.info(f"벤치마크 상품 저장 완료: {product_data['name']} (임베딩={'성공' if embedding else '실패'})")
        return saved_id

    async def analyze_product(self, benchmark_id: Any):
        """
        Triggers SourcingAgent to analyze the benchmark product and persist results.
        """
        from app.services.ai.agents.sourcing_agent import SourcingAgent
        from app.db import SessionLocal
        
        logger.info(f"AI 분석 트리거: {benchmark_id}")
        with SessionLocal() as db:
            agent = SourcingAgent(db)
            product = db.get(BenchmarkProduct, benchmark_id)
            if not product:
                logger.error(f"분석할 상품을 찾을 수 없습니다: {benchmark_id}")
                return
            
            # Simple input for analyze_benchmark
            input_data = {
                "name": product.name,
                "detail_html": product.detail_html,
                "price": product.price,
                "images": product.image_urls or [],
                "reviews": product.raw_data.get("reviews") or []
            }
            
            # We call analyze_benchmark directly via the agent's run-like state preparation or just invoke a node
            # For simplicity, we can use the 'run' method but it executes the whole graph.
            # If we only want analysis, we can call agent.analyze_benchmark manually.
            # But the 'run' method ensures all fields are populated in state.
            try:
                # We wrap the sync analyze_benchmark if needed, but it's sync in the agent.
                # Actually SourcingAgent.run is async and uses langgraph.
                await agent.run(str(benchmark_id), input_data)
                logger.info(f"AI 분석 및 학습 완료: {product.name}")
            except Exception as e:
                logger.error(f"AI 분석 중 오류 발생: {e}")


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
            idx_count = idx + 1
            item["quality_score"] = min(10.0, (desc_len / 10000.0) + (img_count * 0.5))
            
            saved_id = await self.save_product(item)
            
            # Optionally trigger AI analysis (e.g. for high quality or first few items)
            if saved_id and idx_count <= 2: # Limit AI calls in bulk for now
                await self.analyze_product(saved_id)

            
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
