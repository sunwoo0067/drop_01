from __future__ import annotations

import re
from app.services.detail_html_normalizer import normalize_ownerclan_html
from app.services.detail_html_checks import strip_forbidden_tags

def normalize_detail_html_for_coupang(html: str) -> str:
    """
    쿠팡 상세페이지 HTML을 정규화합니다.
    - 모든 http:// 주소를 https://로 변환 (쿠팡 제약 사항)
    - 오너클랜 원본 데이터의 제어 문자 제거
    """
    s = str(html or "")
    if not s:
        return s

    # Coupang requires HTTPS for all content
    s = s.replace("http://", "https://")
    
    # Remove hidden control characters often found in source data
    s = normalize_ownerclan_html(s)
    
    # Strip forbidden tags (script, iframe, etc.)
    s = strip_forbidden_tags(s)
    
    return s

def build_coupang_detail_html_from_processed_images(urls: list[str]) -> str:
    safe_urls: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if not isinstance(u, str):
            continue
        s = u.strip()
        if not s:
            continue
        s = normalize_detail_html_for_coupang(s)
        if s in seen:
            continue
        seen.add(s)
        safe_urls.append(s)
        if len(safe_urls) >= 20:
            break

    parts: list[str] = []
    for u in safe_urls:
        parts.append(f'<img src="{u}" style="max-width:100%;height:auto;"> <br>')

    parts.append(
        '<p style="font-size: 12px; color: #777777; display: block; margin: 20px 0;">'
        '본 제품을 구매하시면 원활한 배송을 위해 꼭 필요한 고객님의 개인정보를 (성함, 주소, 전화번호 등)  '
        '택배사 및 제 3업체에서 이용하는 것에 동의하시는 것으로 간주됩니다.<br>'
        '개인정보는 배송 외의 용도로는 절대 사용되지 않으니 안심하시기 바랍니다. 안전하게 배송해 드리겠습니다.'
        '</p>'
    )

    out = " ".join(parts).strip()
    return out[:200000]

def detail_html_has_images(html: str) -> bool:
    if not html:
        return False
    return re.search(r"<img\b", html, re.IGNORECASE) is not None

def find_forbidden_tags(html: str) -> list[str]:
    """
    상세페이지 HTML에서 쿠팡이 금지하는 태그가 포함되어 있는지 확인합니다.
    """
    if not html:
        return []
    forbidden_tags = ["script", "iframe", "embed", "object", "form", "input", "button"]
    found = []
    for tag in forbidden_tags:
        if re.search(rf"<{tag}\b", html, re.IGNORECASE):
            found.append(tag)
    return found

def extract_coupang_image_url(image_obj: dict[str, Any]) -> str | None:
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

    vendor_path = image_obj.get("vendorPath")
    if isinstance(vendor_path, str) and vendor_path.strip():
        vp = vendor_path.strip()
        if vp.startswith("http://") or vp.startswith("https://") or vp.startswith("//"):
            return normalize_detail_html_for_coupang(vp)
        if "/" in vp:
            return _build_coupang_cdn_url(vp)

    cdn_path = image_obj.get("cdnPath")
    if isinstance(cdn_path, str) and cdn_path.strip():
        return _build_coupang_cdn_url(cdn_path.strip())

    return None
