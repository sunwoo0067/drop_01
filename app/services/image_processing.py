import logging
try:
    import cv2
except Exception:
    cv2 = None
import numpy as np
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
import random
import math

from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)

if cv2 is None:
    logger.warning("cv2(OpenCV) 모듈을 불러올 수 없습니다. 이미지 해시 브레이킹을 건너뜁니다.")

class ImageProcessingService:
    
    def extract_images_from_html(self, html_content: str, limit: int = 10) -> List[str]:
        """
        Extracts image URLs from HTML content (e.g. detail page).
        """
        if not html_content:
            return []
            
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            img_tags = soup.find_all("img")
            urls = []
            for img in img_tags:
                src = img.get("src")
                if src:
                    # Basic validation/cleaning
                    if src.startswith("//"):
                        src = "https:" + src

                    src_lower = src.lower()
                    if src_lower.startswith("data:"):
                        continue
                    if not src_lower.startswith(("http://", "https://")):
                        continue
                    
                    # Filter out tiny icons or tracking pixels if possible (naive check by name/ext)
                    if not any(x in src_lower for x in [".gif", "icon", "logo", "pixel", "banner", "event", "promo", "advert", "ads"]):
                        urls.append(src)
                        
                if len(urls) >= limit:
                    break
            return urls
        except Exception as e:
            logger.error(f"Error extracting images from HTML: {e}")
            return []

    def hash_breaking(self, image_api_response_content: bytes) -> Optional[bytes]:
        """
        Applies subtle modifications to the image to break perceptual hashing (Winner System Avoidance).
        1. Decode
        2. Resize slightly (101% - 102%)
        3. Adjust brightness/contrast slightly
        4. Encode back to bytes
        """
        try:
            if cv2 is None:
                return image_api_response_content

            # 1. Decode
            nparr = np.frombuffer(image_api_response_content, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                return None
            try:
                h0, w0 = img.shape[:2]
                if h0 > 10 and w0 > 10:
                    crop_ratio = random.uniform(0.0, 0.06)
                    ch = max(1, int(h0 * (1.0 - crop_ratio)))
                    cw = max(1, int(w0 * (1.0 - crop_ratio)))

                    if ch < h0 and cw < w0:
                        max_y = max(0, h0 - ch)
                        max_x = max(0, w0 - cw)
                        oy = int(max_y * random.uniform(0.35, 0.65)) if max_y > 0 else 0
                        ox = int(max_x * random.uniform(0.35, 0.65)) if max_x > 0 else 0
                        oy = max(0, min(max_y, oy))
                        ox = max(0, min(max_x, ox))

                        img = img[oy : oy + ch, ox : ox + cw]
            except Exception:
                pass
            
            # 2. Resize Control (Coupang requirements: 500x500 ~ 5000x5000)
            height, width = img.shape[:2]
            
            # 해시 브레이킹을 위한 미세 조정 (기존 로직 유지)
            scale = random.uniform(1.01, 1.02)
            new_height, new_width = int(height * scale), int(width * scale)
            
            # 최소/최대 규격 준수 강제 조정
            MIN_DIM = 500
            MAX_DIM = 5000
            
            # 1) 비율을 최대한 유지하면서 min/max 범위로 맞춤
            if new_width < MIN_DIM or new_height < MIN_DIM:
                ratio = max(MIN_DIM / new_width, MIN_DIM / new_height)
                new_width = int(math.ceil(new_width * ratio))
                new_height = int(math.ceil(new_height * ratio))

            if new_width > MAX_DIM or new_height > MAX_DIM:
                ratio = min(MAX_DIM / new_width, MAX_DIM / new_height)
                new_width = int(math.floor(new_width * ratio))
                new_height = int(math.floor(new_height * ratio))

            # 2) max clamp 과정에서 반대 축이 500 미만으로 내려갈 수 있어(예: 세로 5000 제한으로 가로가 <500),
            #    최종적으로 각 축을 독립적으로 [500, 5000]에 맞춥니다(비율이 약간 변형될 수 있음).
            new_width = max(MIN_DIM, min(MAX_DIM, int(new_width)))
            new_height = max(MIN_DIM, min(MAX_DIM, int(new_height)))

            img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)
            
            # 3. Brightness/Contrast Adjustment (Random minimal)
            alpha = random.uniform(0.98, 1.02) # Contrast
            beta = random.randint(-5, 5)       # Brightness
            img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)
            
            # 4. Strip Metadata (decode/encode로 제거) & Encode
            # - 쿠팡 기타이미지(DETAIL) 규격: 최대 10MB, 최소 500x500, 최대 5000x5000
            MAX_BYTES = 10 * 1024 * 1024

            quality = 90
            while quality >= 30:
                success, encoded_img = cv2.imencode(
                    ".jpg",
                    img,
                    [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)],
                )
                if not success:
                    return None

                out = encoded_img.tobytes()
                if len(out) <= MAX_BYTES:
                    return out

                quality -= 10

            # 품질을 최저로 낮춰도 10MB 초과하면 다운스케일 시도
            MIN_DIM = 500
            MAX_DIM = 5000
            for _ in range(6):
                h, w = img.shape[:2]
                if h <= MIN_DIM or w <= MIN_DIM:
                    break

                scale2 = 0.9
                nh = max(MIN_DIM, int(h * scale2))
                nw = max(MIN_DIM, int(w * scale2))
                nh = min(nh, MAX_DIM)
                nw = min(nw, MAX_DIM)

                if nh == h and nw == w:
                    break

                img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LANCZOS4)

                quality = 80
                while quality >= 30:
                    success, encoded_img = cv2.imencode(
                        ".jpg",
                        img,
                        [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)],
                    )
                    if not success:
                        return None

                    out = encoded_img.tobytes()
                    if len(out) <= MAX_BYTES:
                        return out
                    quality -= 10

            return None
            
        except Exception as e:
            logger.error(f"Error in hash breaking: {e}")
            return None

    def process_and_upload_images(self, image_urls: List[str], detail_html: str = "", product_id: str = "temp") -> List[str]:
        """
        Main pipeline:
        1. Check image count, supplement from HTML if < 5.
        2. Download -> Hash Break -> Upload to Supabase.
        3. Return new URLs.
        """
        target_count = 5
        processed_urls = []
        stats = {
            "target_count": target_count,
            "input_count": len(image_urls or []),
            "supplemented_from_html": 0,
            "unique_candidates": 0,
            "download_ok": 0,
            "download_fail": 0,
            "hash_break_fail": 0,
            "upload_ok": 0,
            "upload_fail": 0,
            "exceptions": 0,
        }
        
        # 1. Supplement Images
        candidates = image_urls[:]
        
        # Deduplicate initial candidates
        seen = set()
        unique_candidates = []
        for url in candidates:
            if url and url not in seen:
                unique_candidates.append(url)
                seen.add(url)
        
        # If not enough images, try to extract from detail HTML
        if len(unique_candidates) < target_count and detail_html:
            logger.info(f"Not enough images ({len(unique_candidates)}/{target_count}), extracting from detail HTML...")
            # Extract enough to fulfill target + some buffer
            extra_images = self.extract_images_from_html(detail_html, limit=15) 
            
            added_count = 0
            for img_url in extra_images:
                if img_url not in seen:
                    unique_candidates.append(img_url)
                    seen.add(img_url)
                    added_count += 1
            
            stats["supplemented_from_html"] = added_count
            logger.info(f"Extracted {added_count} new images from HTML. Total unique candidates: {len(unique_candidates)}")

        stats["unique_candidates"] = len(unique_candidates)
        
        # 2. Process
        logger.info(f"Processing {len(unique_candidates)} images for product {product_id}...")
        
        for i, url in enumerate(unique_candidates):
            if len(processed_urls) >= 10: # Safety cap
                break
            try:
                # Download
                resp = requests.get(url, timeout=10)
                if resp.status_code != 200:
                    stats["download_fail"] += 1
                    continue

                stats["download_ok"] += 1

                original_bytes = resp.content

                remaining_needed = max(0, target_count - len(processed_urls))
                remaining_sources = max(1, len(unique_candidates) - i)
                variants_to_make = max(1, int(math.ceil(remaining_needed / remaining_sources)))
                variants_to_make = min(variants_to_make, 5)

                for _ in range(variants_to_make):
                    if len(processed_urls) >= 10:
                        break
                    if len(processed_urls) >= target_count:
                        break

                    # Hash Breaking
                    processed_bytes = self.hash_breaking(original_bytes)
                    if not processed_bytes:
                        logger.warning(f"해시 브레이킹/규격 변환 실패(url={url})")
                        stats["hash_break_fail"] += 1
                        continue

                    # Upload
                    new_url = storage_service.upload_image(
                        processed_bytes,
                        path_prefix=f"market_processing/{product_id}"
                    )

                    if new_url:
                        processed_urls.append(new_url)
                        stats["upload_ok"] += 1
                    else:
                        stats["upload_fail"] += 1
                    
            except Exception as e:
                stats["exceptions"] += 1
                logger.error(f"이미지 처리 실패(url={url}): {e}")
                
        logger.info(
            "이미지 처리 요약(productId=%s, target=%s, input=%s, unique=%s, fromHtml=%s, downloadOk=%s, downloadFail=%s, hashFail=%s, uploadOk=%s, uploadFail=%s, exceptions=%s, result=%s)",
            product_id,
            stats["target_count"],
            stats["input_count"],
            stats["unique_candidates"],
            stats["supplemented_from_html"],
            stats["download_ok"],
            stats["download_fail"],
            stats["hash_break_fail"],
            stats["upload_ok"],
            stats["upload_fail"],
            stats["exceptions"],
            len(processed_urls),
        )

        if (
            len(processed_urls) < target_count
            or stats["download_fail"] > 0
            or stats["upload_fail"] > 0
            or stats["exceptions"] > 0
        ):
            logger.warning(
                "이미지 처리 경고(productId=%s, target=%s, input=%s, unique=%s, fromHtml=%s, downloadOk=%s, downloadFail=%s, hashFail=%s, uploadOk=%s, uploadFail=%s, exceptions=%s, result=%s)",
                product_id,
                stats["target_count"],
                stats["input_count"],
                stats["unique_candidates"],
                stats["supplemented_from_html"],
                stats["download_ok"],
                stats["download_fail"],
                stats["hash_break_fail"],
                stats["upload_ok"],
                stats["upload_fail"],
                stats["exceptions"],
                len(processed_urls),
            )

        return processed_urls

image_processing_service = ImageProcessingService()
