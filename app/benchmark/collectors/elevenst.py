from __future__ import annotations

import logging
import json
import re
from typing import Any

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.benchmark_collector import BenchmarkCollector as CoupangBenchmarkCollector
from app.settings import settings


logger = logging.getLogger(__name__)


class ElevenstBenchmarkCollector:
    def __init__(self, market_code: str = "ELEVENST") -> None:
        self.market_code = market_code
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self._saver = CoupangBenchmarkCollector(market_code=market_code)

    async def collect_ranking(self, limit: int = 100, category_url: str | None = None) -> list[dict[str, Any]]:
        url = (
            str(category_url).strip()
            if category_url
            else "https://www.11st.co.kr/browsing/BestSeller.tmall?method=getBestSellerMain"
        )

        html = ""
        if settings.ownerclan_use_self_proxy:
            status, html = await self._saver._fetch_via_proxy(url)
            if status != 200:
                logger.error(f"11번가 랭킹 페이지 수집 실패 (Proxy): HTTP {status} (url={url})")
                return []
        else:
            async with AsyncSession(impersonate="chrome", headers=self.headers) as client:
                resp = await client.get(url, allow_redirects=True)
                if resp.status_code != 200:
                    logger.error(f"11번가 랭킹 페이지 수집 실패: HTTP {resp.status_code} (url={url})")
                    return []
                html = resp.text or ""

        soup = BeautifulSoup(html, "html.parser")

        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for a in soup.select('a[href*="/products/"]'):
            href = a.get("href") or ""
            m = re.search(r"/products/(\d+)", href)
            if not m:
                continue
            prd_no = m.group(1)
            if prd_no in seen:
                continue

            li = a.find_parent("li")
            container = li if li is not None else a
            text = re.sub(r"\s+", " ", container.get_text(" ", strip=True)).strip()
            if not re.match(r"^\d+\s+", text):
                continue

            raw_name = a.get_text(" ", strip=True) or ""
            name = raw_name.strip() or None
            if not name or any(tok in name for tok in ("정상가", "판매가", "무료배송")):
                base = text
                cut_idx = None
                for token in ("정상가", "판매가"):
                    idx = base.find(token)
                    if idx != -1:
                        cut_idx = idx if cut_idx is None else min(cut_idx, idx)
                if cut_idx is not None:
                    base = base[:cut_idx]
                base = re.sub(r"\s+", " ", base).strip()
                base = re.sub(r"^\d+\s+", "", base).strip()
                name = base or a.get("title") or f"11st-{prd_no}"

            name = re.sub(r"\s+", " ", str(name)).strip()

            price = 0
            m_price = re.search(r"판매가\s*([0-9,]+)\s*원", text)
            if m_price:
                try:
                    price = int(m_price.group(1).replace(",", ""))
                except Exception:
                    price = 0
            if price <= 0:
                m_price2 = re.search(r"\b([0-9]{1,3}(?:,[0-9]{3})*)\s*원\b", text)
                if m_price2:
                    try:
                        price = int(m_price2.group(1).replace(",", ""))
                    except Exception:
                        price = 0

            product_url = f"https://www.11st.co.kr/products/{prd_no}"

            items.append(
                {
                    "product_id": prd_no,
                    "name": name,
                    "price": price,
                    "product_url": product_url,
                    "raw_ranking_text": text,
                }
            )
            seen.add(prd_no)
            if len(items) >= limit:
                break

        return items

    async def collect_detail(self, product_url: str) -> dict[str, Any]:
        url = str(product_url).strip()
        if not url:
            return {"detail_html": "", "image_urls": [], "raw_html": ""}

        html = ""
        if settings.ownerclan_use_self_proxy:
            status, html = await self._saver._fetch_via_proxy(url)
            if status != 200:
                logger.error(f"11번가 상세 페이지 수집 실패 (Proxy): HTTP {status} (url={url})")
                return {"detail_html": "", "image_urls": [], "raw_html": html or ""}
        else:
            async with AsyncSession(impersonate="chrome", headers=self.headers) as client:
                resp = await client.get(url, allow_redirects=True)
                if resp.status_code != 200:
                    logger.error(f"11번가 상세 페이지 수집 실패: HTTP {resp.status_code} (url={url})")
                    return {"detail_html": "", "image_urls": [], "raw_html": resp.text or ""}
                html = resp.text or ""

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
            soup.select_one("#tabpanelPrdInfo")
            or soup.select_one("#tabContents")
            or soup.select_one("#prdInfo")
            or soup.select_one("#productInfo")
            or soup.select_one("#productDetail")
        )
        detail_html = str(detail_node) if detail_node else ""

        if not detail_html:
            desc = json_ld_description or description
            if desc:
                detail_html = f"<div>{desc}</div>"

        return {"detail_html": detail_html, "image_urls": image_urls, "raw_html": html}

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
