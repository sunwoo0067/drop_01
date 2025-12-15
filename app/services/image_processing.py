import logging
import cv2
import numpy as np
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
import random

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
        
        # 1. Supplement Images
        candidates = image_urls[:]
        if len(candidates) < target_count and detail_html:
            logger.info(f"Not enough images ({len(candidates)}), extracting from detail HTML...")
            extra_images = self.extract_images_from_html(detail_html, limit=target_count - len(candidates) + 5) # Get a few more to be safe
            candidates.extend(extra_images)
            
        # Deduplicate
        seen = set()
        unique_candidates = []
        for url in candidates:
            if url not in seen:
                unique_candidates.append(url)
                seen.add(url)
        
        # 2. Process
        logger.info(f"Processing {len(unique_candidates)} images for product {product_id}...")
        
        for i, url in enumerate(unique_candidates):
            if len(processed_urls) >= 10: # Safety cap
                break
                
            try:
                # Download
                resp = requests.get(url, timeout=10)
                if resp.status_code != 200:
                    continue
                
                # Hash Breaking
                processed_bytes = self.hash_breaking(resp.content)
                if not processed_bytes:
                    # Fallback to original if processing fails (e.g. invalid format)
                    logger.warning(f"Hash breaking failed for {url}, using original.")
                    processed_bytes = resp.content
                
                # Upload
                new_url = storage_service.upload_image(
                    processed_bytes, 
                    path_prefix=f"market_processing/{product_id}"
                )
                
                if new_url:
                    processed_urls.append(new_url)
                    
            except Exception as e:
                logger.error(f"Failed to process image {url}: {e}")
                
        return processed_urls

image_processing_service = ImageProcessingService()
