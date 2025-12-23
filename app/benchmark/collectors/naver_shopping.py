from __future__ import annotations

import logging
import json
import re
from typing import Any

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.benchmark_collector import BenchmarkCollector as SaverCollector
from app.settings import settings


logger = logging.getLogger(__name__)


class NaverShoppingBenchmarkCollector:
    def __init__(self, market_code: str = "NAVER_SHOPPING") -> None:
        self.market_code = market_code
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self._saver = SaverCollector(market_code=market_code)

    async def collect_ranking(self, limit: int = 100, category_url: str | None = None) -> list[dict[str, Any]]:
        url = (
            str(category_url).strip()
            if category_url
            else "https://snxbest.naver.com/product/best/click"
        )

        html = ""
        if settings.ownerclan_use_sef_proxy:
            status, html = await self._saver._fetch_via_proxy(url)
            if status != 200:
                logger.error(f"네이버쇼핑 BEST 수집 실패 (Proxy): HTTP {status} (url={url})")
                return []
        else:
            async with AsyncSession(impersonate="chrome", headers=self.headers) as client:
                resp = await client.get(url, allow_redirects=True)
                if resp.status_code != 200:
                    logger.error(f"네이버쇼핑 BEST 수집 실패: HTTP {resp.status_code} (url={url})")
                    return []
                html = resp.text or ""

        soup = BeautifulSoup(html, "html.parser")

        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for a in soup.select('a[href*="smartstore.naver.com/main/products/"]'):
            href = (a.get("href") or "").strip()
            m = re.search(r"/products/(\d+)", href)
            if not m:
                continue
            product_id = m.group(1)
            if product_id in seen:
                continue

            container = a
            for _ in range(4):
                parent = container.parent
                if not parent:
                    break
                container = parent

            text = container.get_text(" ", strip=True)
            name = a.get_text(" ", strip=True) or None
            if not name:
                m_name = re.search(r"찜하기\s*([^0-9]+?)\s*(?:원가|[0-9,]+원)", text)
                name = m_name.group(1).strip() if m_name else None
            if not name:
                name = f"naver-{product_id}"

            price = 0
            m_sale = re.search(r"할인율\s*\d+%\s*([0-9]{1,3}(?:,[0-9]{3})*)\s*원", text)
            if m_sale:
                try:
                    price = int(m_sale.group(1).replace(",", ""))
                except Exception:
                    price = 0
            if price <= 0:
                m_price = re.search(r"\b([0-9]{1,3}(?:,[0-9]{3})*)\s*원\s*(?:무료배송|네이버배송)", text)
                if m_price:
                    try:
                        price = int(m_price.group(1).replace(",", ""))
                    except Exception:
                        price = 0
            if price <= 0:
                prices = re.findall(r"([0-9]{1,3}(?:,[0-9]{3})*)\s*원", text)
                if prices:
                    try:
                        price = int(prices[0].replace(",", ""))
                    except Exception:
                        price = 0

            items.append(
                {
                    "product_id": product_id,
                    "name": name,
                    "price": price,
                    "product_url": href,
                    "raw_ranking_text": text,
                }
            )
            seen.add(product_id)
            if len(items) >= limit:
                break

        return items

    async def collect_trending_keywords(self) -> list[str]:
        """
        Collects trending keywords from Naver Shopping BEST.
        """
        items = await self.collect_ranking(limit=50)
        keywords: set[str] = set()
        for item in items:
            name = item.get("name") or ""
            # Simple keyword extraction: split by space and take 2+ char words
            words = [w.strip() for w in name.split() if len(w.strip()) >= 2]
            # Take first 2-3 significant words as candidate keywords
            if words:
                keywords.add(" ".join(words[:2]))
        return list(keywords)

    async def collect_reviews(self, product_id: str, limit: int = 10) -> list[str]:
        """
        Collects customer reviews for a specific product.
        """
        # Naver SmartStore Review API endpoint (Common pattern)
        url = f"https://smartstore.naver.com/v1/products/{product_id}/reviews?page=1&size={limit}&sortType=REVIEW_RANKING"
        
        try:
            if settings.ownerclan_use_sef_proxy:
                status, raw = await self._saver._fetch_via_proxy(url)
                if status != 200:
                    return []
                data = json.loads(raw)
            else:
                async with AsyncSession(impersonate="chrome", headers=self.headers) as client:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        return []
                    data = resp.json()
            
            reviews = []
            for item in data.get("contents", []):
                content = item.get("reviewContent")
                if content:
                    reviews.append(content)
            return reviews
        except Exception as e:
            logger.error(f"Failed to collect reviews for {product_id}: {e}")
            return []

    async def collect_detail(self, product_url: str) -> dict[str, Any]:
        url = str(product_url).strip()
        if not url:
            return {"detail_html": "", "image_urls": [], "raw_html": ""}

        html = ""
        blocked_reason: str | None = None
        
        if settings.ownerclan_use_sef_proxy:
            status, html = await self._saver._fetch_via_proxy(url)
            if status != 200:
                logger.error(f"네이버 스마트스토어 상세 수집 실패 (Proxy): HTTP {status} (url={url})")
                if status in (490, 403):
                    blocked_reason = "CAPTCHA"
                return {
                    "detail_html": "",
                    "image_urls": [],
                    "raw_html": html,
                    "blocked_reason": blocked_reason,
                }
        else:
            async with AsyncSession(impersonate="chrome", headers=self.headers) as client:
                resp = await client.get(url, allow_redirects=True)
                if resp.status_code != 200:
                    logger.error(f"네이버 스마트스토어 상세 수집 실패: HTTP {resp.status_code} (url={url})")
                    if resp.status_code in (490, 403):
                        blocked_reason = "CAPTCHA"
                    return {
                        "detail_html": "",
                        "image_urls": [],
                        "raw_html": resp.text or "",
                        "blocked_reason": blocked_reason,
                    }
                html = resp.text or ""

        if ("ncpt.naver.com" in html) or ("WtmCaptcha" in html) or ("title=\"captcha\"" in html):
            logger.error(f"네이버 스마트스토어 상세 수집 차단(CAPTCHA): url={url}")
            return {"detail_html": "", "image_urls": [], "raw_html": html, "blocked_reason": "CAPTCHA"}
        soup = BeautifulSoup(html, "html.parser")

        description: str | None = None
        for meta in soup.select('meta[property="og:description"], meta[name="description"], meta[name="og:description"]'):
            content = (meta.get("content") or "").strip()
            if content:
                description = content
                break

        image_urls: list[str] = []
        for meta in soup.select(
            'meta[property="og:image"], meta[property="og:image:secure_url"], meta[name="og:image"], '
            'meta[property="twitter:image"], meta[name="twitter:image"], meta[itemprop="image"], link[rel="image_src"]'
        ):
            content = (meta.get("content") or meta.get("href") or "").strip()
            if content:
                image_urls.append(content)

        json_ld_description: str | None = None
        json_ld_images: list[str] = []
        for script in soup.select('script[type="application/ld+json"]'):
            raw = (script.string or script.get_text() or "").strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue

            candidates = data if isinstance(data, list) else [data]
            for obj in candidates:
                if not isinstance(obj, dict):
                    continue
                if json_ld_description is None and isinstance(obj.get("description"), str):
                    json_ld_description = obj.get("description")
                img = obj.get("image")
                if isinstance(img, str):
                    json_ld_images.append(img)
                elif isinstance(img, list):
                    for it in img:
                        if isinstance(it, str):
                            json_ld_images.append(it)

        if not image_urls and json_ld_images:
            image_urls = json_ld_images

        normalized: list[str] = []
        for u in image_urls:
            if u.startswith("//"):
                normalized.append("https:" + u)
            else:
                normalized.append(u)
        image_urls = list(dict.fromkeys(normalized))

        detail_node = (
            soup.select_one("#INTRODUCE")
            or soup.select_one("#productDetail")
            or soup.select_one("#content")
            or soup.select_one("#wrap")
        )
        detail_html = str(detail_node) if detail_node else ""

        if not detail_html:
            desc = json_ld_description or description
            if desc:
                detail_html = f"<div>{desc}</div>"

        # Try to extract product_id for reviews
        m = re.search(r"/products/(\d+)", url)
        reviews = []
        if m:
            product_id = m.group(1)
            reviews = await self.collect_reviews(product_id)

        return {
            "detail_html": detail_html, 
            "image_urls": image_urls, 
            "raw_html": html,
            "reviews": reviews
        }

    async def run_ranking_collection(self, limit: int = 10, category_url: str | None = None, job_id: Any = None):
        items = await self.collect_ranking(limit=limit, category_url=category_url)
        total = len(items)
        
        from app.models import BenchmarkCollectJob
        from app.db import SessionLocal

        for idx, item in enumerate(items):
            logger.info(f"Processing {item.get('name')} ({idx+1}/{total})...")
            details = await self.collect_detail(str(item.get("product_url") or ""))
            if details:
                item.update(details)
            
            # Simple quality score heuristic
            desc_len = len(item.get("detail_html") or "")
            img_count = len(item.get("image_urls") or [])
            item["quality_score"] = min(10.0, (desc_len / 10000.0) + (img_count * 0.5))
            
            await self._saver.save_product(item)

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
