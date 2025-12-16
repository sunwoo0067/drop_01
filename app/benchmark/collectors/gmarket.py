from __future__ import annotations

import logging
import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from app.benchmark_collector import BenchmarkCollector as SaverCollector

logger = logging.getLogger(__name__)


class GmarketBenchmarkCollector:
    def __init__(self, market_code: str = "GMARKET") -> None:
        self.market_code = market_code
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self._saver = SaverCollector(market_code=market_code)

    async def collect_ranking(self, limit: int = 100, category_url: str | None = None) -> list[dict[str, Any]]:
        url = str(category_url).strip() if category_url else "https://www.gmarket.co.kr/n/best"

        async with AsyncSession(impersonate="chrome", headers=self.headers) as client:
            resp = await client.get(url, allow_redirects=True)

        if resp.status_code != 200:
            logger.error(f"G마켓 베스트 수집 실패: HTTP {resp.status_code} (url={url})")
            return []

        html = resp.text or ""
        soup = BeautifulSoup(html, "html.parser")

        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _extract_goodscode(href: str) -> str | None:
            m = re.search(r"goodscode=([0-9]+)", href)
            if m:
                return m.group(1)
            m2 = re.search(r"/Item\?goodscode=([0-9]+)", href)
            if m2:
                return m2.group(1)
            return None

        for a in soup.select('a[href*="goodscode="]'):
            href = (a.get("href") or "").strip()
            goodscode = _extract_goodscode(href)
            if not goodscode:
                continue
            if goodscode in seen:
                continue

            li = a.find_parent("li")
            container = li if li is not None else a
            text = container.get_text(" ", strip=True)
            name = a.get_text(" ", strip=True) or None
            if not name:
                name = f"gmarket-{goodscode}"

            price = 0
            m_sale = re.search(r"판매가\s*([0-9]{1,3}(?:,[0-9]{3})*)\s*원", text)
            if m_sale:
                try:
                    price = int(m_sale.group(1).replace(",", ""))
                except Exception:
                    price = 0
            if price <= 0:
                prices = re.findall(r"([0-9]{1,3}(?:,[0-9]{3})*)\s*원", text)
                if prices:
                    try:
                        price = int(prices[-1].replace(",", ""))
                    except Exception:
                        price = 0

            product_url = href
            if product_url.startswith("//"):
                product_url = "https:" + product_url
            if product_url.startswith("/"):
                product_url = "https://www.gmarket.co.kr" + product_url

            items.append(
                {
                    "product_id": goodscode,
                    "name": name,
                    "price": price,
                    "product_url": product_url,
                    "raw_ranking_text": text,
                }
            )
            seen.add(goodscode)
            if len(items) >= limit:
                break

        return items

    async def collect_detail(self, product_url: str) -> dict[str, Any]:
        url = str(product_url).strip()
        if not url:
            return {"detail_html": "", "image_urls": [], "raw_html": ""}

        async with AsyncSession(impersonate="chrome", headers=self.headers) as client:
            resp = await client.get(url, allow_redirects=True)

        if resp.status_code != 200:
            logger.error(f"G마켓 상세 수집 실패: HTTP {resp.status_code} (url={url})")
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

        detail_html = ""
        raw_html_to_store = html
        detail_iframe = (
            soup.select_one("iframe#detail1")
            or soup.select_one('iframe[src*="ItemDetailV2"]')
            or soup.select_one('iframe[src*="ItemDetail"]')
        )
        if detail_iframe is not None:
            src = (detail_iframe.get("src") or "").strip()
            if src and src != "about:blank":
                iframe_url = urljoin(url, src)
                async with AsyncSession(impersonate="chrome", headers=self.headers) as client:
                    iframe_resp = await client.get(iframe_url, allow_redirects=True)
                if iframe_resp.status_code == 200 and (iframe_resp.text or "").strip():
                    iframe_soup = BeautifulSoup(iframe_resp.text or "", "html.parser")
                    body = iframe_soup.body if iframe_soup.body is not None else iframe_soup
                    detail_html = str(body)
                    raw_html_to_store = iframe_resp.text or raw_html_to_store

        if not detail_html:
            detail_node = soup.select_one("#goodsDetail") or soup.select_one("#detail")
            detail_html = str(detail_node) if detail_node else ""

        if not detail_html and description:
            detail_html = f"<div>{description}</div>"

        return {"detail_html": detail_html, "image_urls": image_urls, "raw_html": raw_html_to_store}

    async def run_ranking_collection(self, limit: int = 10, category_url: str | None = None):
        items = await self.collect_ranking(limit=limit, category_url=category_url)
        for item in items:
            details = await self.collect_detail(str(item.get("product_url") or ""))
            if details:
                item.update(details)
            await self._saver.save_product(item)
