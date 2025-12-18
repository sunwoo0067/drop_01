import logging
import cv2
import numpy as np
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
import random
import math

from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)

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
                    
                    # Filter out tiny icons or tracking pixels if possible (naive check by name/ext)
                    if not any(x in src.lower() for x in [".gif", "icon", "logo", "pixel"]):
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
            # 1. Decode
            nparr = np.frombuffer(image_api_response_content, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                return None
            
            # 2. Resize (Zoom in/Scale up slightly)
            scale = random.uniform(1.01, 1.02) # 1% ~ 2%
            height, width = img.shape[:2]
            new_height, new_width = int(height * scale), int(width * scale)
            img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)
            
            # Crop back to roughly original or keep scaled (Keeping scaled is fine for now, usually better quality)
            # Let's crop center to remove potential border artifacts if we want original size, 
            # but usually just resizing is enough to break hash. 
            # To be safe, let's crop the center to original size to avoid weird aspect ratios if we just stretched.
            # start_h = (new_height - height) // 2
            # start_w = (new_width - width) // 2
            # img = img[start_h:start_h+height, start_w:start_w+width]

            # 3. Brightness/Contrast Adjustment (Random minimal)
            alpha = random.uniform(0.98, 1.02) # Contrast
            beta = random.randint(-5, 5)       # Brightness
            img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)
            
            # 4. Strip Metadata (Implicit by decoding/encoding) & Encode
            success, encoded_img = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            if not success:
                return None
                
            return encoded_img.tobytes()
            
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
        if len(candidates) < target_count and detail_html:
            logger.info(f"Not enough images ({len(candidates)}), extracting from detail HTML...")
            extra_images = self.extract_images_from_html(detail_html, limit=target_count - len(candidates) + 5) # Get a few more to be safe
            candidates.extend(extra_images)
            stats["supplemented_from_html"] = len(extra_images or [])
            
        # Deduplicate
        seen = set()
        unique_candidates = []
        for url in candidates:
            if url not in seen:
                unique_candidates.append(url)
                seen.add(url)

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
                        logger.warning(f"Hash breaking failed for {url}, using original.")
                        stats["hash_break_fail"] += 1
                        processed_bytes = original_bytes

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
