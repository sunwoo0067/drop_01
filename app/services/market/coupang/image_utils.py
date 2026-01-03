from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session
from app.models import Product, SupplierItemRaw
from app.services.market.coupang.html_utils import normalize_detail_html_for_coupang

logger = logging.getLogger(__name__)

def get_original_image_urls(session: Session, product: Product) -> list[str]:
    """
    원본 상품 데이터에서 이미지 URL 목록을 추출합니다.
    """
    if not product.supplier_item_id:
        return []
    
    supplier_item = session.get(SupplierItemRaw, product.supplier_item_id)
    if not supplier_item or not isinstance(supplier_item.raw, dict):
        return []
        
    # 기존 global/helper 함수 호출 (필요시 내부 구현으로 이동)
    from app.services.coupang_ready_service import collect_image_urls_from_raw
    return collect_image_urls_from_raw(supplier_item.raw)

def extract_coupang_image_url(image_obj: dict[str, Any]) -> str | None:
    """
    쿠팡 이미지 객체에서 CDN URL을 추출 또는 생성합니다.
    """
    if not isinstance(image_obj, dict):
        return None

    def _build_coupang_cdn_url(path: str) -> str:
        s = str(path or "").strip()
        if not s:
            return s
        if s.startswith("http://") or s.startswith("https://") or s.startswith("//"):
            return normalize_detail_html_for_coupang(s)
        s = s.lstrip("/")
        if s.startswith("image/"):
            return "https://image1.coupangcdn.com/" + s
        return "https://image1.coupangcdn.com/image/" + s

    # vendorPath 우선 확인
    vendor_path = image_obj.get("vendorPath")
    if isinstance(vendor_path, str) and vendor_path.strip():
        vp = vendor_path.strip()
        if vp.startswith("http://") or vp.startswith("https://") or vp.startswith("//"):
            return normalize_detail_html_for_coupang(vp)
        if "/" in vp:
            return _build_coupang_cdn_url(vp)

    # cdnPath 확인
    cdn_path = image_obj.get("cdnPath")
    if isinstance(cdn_path, str) and cdn_path.strip():
        return _build_coupang_cdn_url(cdn_path.strip())

    return None

def build_contents_image_blocks(image_urls: list[str]) -> list[dict[str, Any]]:
    """
    상세페이지용 이미지 블록을 생성합니다.
    """
    if not image_urls:
        return []
        
    return [
        {
            "contentsType": "IMAGE_NO_SPACE",
            "contentDetails": [
                {"content": url, "detailType": "IMAGE"}
                for url in image_urls[:20]
            ],
        }
    ]
