import logging
try:
    import cv2
except Exception:
    cv2 = None
import numpy as np
import requests
import httpx
import asyncio
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from typing import List, Optional, Tuple
import random
import math

from app.services.storage_service import storage_service
from app.services.image_validation import validate_image_bytes

logger = logging.getLogger(__name__)

if cv2 is None:
    logger.warning("cv2(OpenCV) 모듈을 불러올 수 없습니다. 이미지 해시 브레이킹을 건너뜁니다.")

class ImageProcessingService:
    def _build_referer(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}/"
        except Exception:
            return ""
        return ""

    def _download_image(self, url: str) -> bytes | None:
        headers = {
            "User-Agent": "Mozilla/5.0",
        }
        referer = self._build_referer(url)
        if referer:
            headers["Referer"] = referer

        resp = None
        for _ in range(2):
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.content
        if url.startswith("http://"):
            https_url = "https://" + url[len("http://") :]
            referer = self._build_referer(https_url)
            if referer:
                headers["Referer"] = referer
            resp = requests.get(https_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.content
        return None

    async def _download_image_async(self, url: str, client: httpx.AsyncClient) -> bytes | None:
        headers = {
            "User-Agent": "Mozilla/5.0",
        }
        referer = self._build_referer(url)
        if referer:
            headers["Referer"] = referer

        for _ in range(2):
            try:
                resp = await client.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return resp.content
            except Exception as e:
                logger.debug(f"Download attempt failed for {url}: {e}")
                continue
        
        if url.startswith("http://"):
            https_url = "https://" + url[len("http://") :]
            referer = self._build_referer(https_url)
            if referer:
                headers["Referer"] = referer
            try:
                resp = await client.get(https_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return resp.content
            except Exception as e:
                logger.debug(f"HTTPS download attempt failed for {https_url}: {e}")
        return None

    def replace_html_image_urls(
        self,
        html_content: str,
        product_id: str = "temp",
        limit: int = 20,
    ) -> tuple[str, list[str]]:
        if not html_content:
            return html_content, []

        soup = BeautifulSoup(html_content, "html.parser")
        base_tag = soup.find("base", href=True)
        base_url = base_tag["href"].strip() if base_tag else ""
        img_tags = soup.find_all("img")
        if not img_tags:
            return html_content, []

        mapping: dict[str, str] = {}
        uploaded: list[str] = []
        for img in img_tags:
            if len(mapping) >= limit:
                break
            src = img.get("src")
            if not src:
                continue
            src = src.strip()
            if not src or src.lower().startswith("data:"):
                continue
            if src.startswith("//"):
                src = "https:" + src
            elif not src.lower().startswith(("http://", "https://")) and base_url:
                src = urljoin(base_url, src)
            if not src.lower().startswith(("http://", "https://")):
                continue
            if src in mapping:
                continue

            original_bytes = self._download_image(src)
            if not original_bytes:
                continue

            validation = validate_image_bytes(original_bytes)
            if not validation.ok:
                logger.warning(
                    "상세 이미지 검증 실패(url=%s, reason=%s, size=%s, width=%s, height=%s)",
                    src,
                    validation.reason,
                    validation.size_bytes,
                    validation.width,
                    validation.height,
                )
                continue

            new_url = storage_service.upload_image(
                original_bytes,
                path_prefix=f"market_detail/{product_id}"
            )
            if not new_url:
                continue

            mapping[src] = new_url
            uploaded.append(new_url)

        if not mapping:
            return html_content, []

        for img in img_tags:
            src = img.get("src")
            if not src:
                continue
            src = src.strip()
            if src.startswith("//"):
                src = "https:" + src
            elif not src.lower().startswith(("http://", "https://")) and base_url:
                src = urljoin(base_url, src)
            if src in mapping:
                img["src"] = mapping[src]

        return str(soup), uploaded
    
    def extract_images_from_html(self, html_content: str, limit: int = 10) -> List[str]:
        """
        Extracts image URLs from HTML content (e.g. detail page).
        """
        if not html_content:
            return []
            
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            base_tag = soup.find("base", href=True)
            base_url = base_tag["href"].strip() if base_tag else ""
            img_tags = soup.find_all("img")
            urls = []
            for img in img_tags:
                src = img.get("src")
                if src:
                    # Basic validation/cleaning
                    if src.startswith("//"):
                        src = "https:" + src
                    elif not src.lower().startswith(("http://", "https://")) and base_url:
                        src = urljoin(base_url, src)

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

    def process_and_upload_images(
        self,
        image_urls: List[str],
        detail_html: str = "",
        product_id: str = "temp",
        max_images: int = 9,
    ) -> List[str]:
        """
        Main pipeline:
        1. De-duplicate and keep original images only.
        2. Download -> Upload to Supabase.
        3. Return new URLs (max 9).
        """
        max_images = max(1, int(max_images))
        max_images = min(max_images, 9)
        processed_urls = []
        candidates = image_urls[:]
        html_images = self.extract_images_from_html(detail_html, limit=20)
        if html_images:
            candidates.extend(html_images)

        stats = {
            "target_count": max_images,
            "input_count": len(candidates),
            "unique_candidates": 0,
            "download_ok": 0,
            "download_fail": 0,
            "upload_ok": 0,
            "upload_fail": 0,
            "exceptions": 0,
            "validation_fail": 0,
            "validation_failures": {},
        }
        
        # Deduplicate initial candidates
        seen = set()
        unique_candidates = []
        for url in candidates:
            if url and url not in seen:
                unique_candidates.append(url)
                seen.add(url)

        stats["unique_candidates"] = len(unique_candidates)
        
        # 2. Process
        logger.info(f"Processing {len(unique_candidates)} images for product {product_id}...")
        
        for i, url in enumerate(unique_candidates):
            if len(processed_urls) >= max_images:
                break
            try:
                original_bytes = self._download_image(url)
                if not original_bytes:
                    stats["download_fail"] += 1
                    continue

                stats["download_ok"] += 1

                validation = validate_image_bytes(original_bytes)
                if not validation.ok:
                    stats["validation_fail"] += 1
                    reason = validation.reason or "unknown"
                    stats["validation_failures"][reason] = stats["validation_failures"].get(reason, 0) + 1
                    logger.warning(
                        "이미지 검증 실패(url=%s, reason=%s, size=%s, width=%s, height=%s)",
                        url,
                        validation.reason,
                        validation.size_bytes,
                        validation.width,
                        validation.height,
                    )
                    stats["download_fail"] += 1
                    continue

                # Upload original bytes (no hash breaking)
                new_url = storage_service.upload_image(
                    original_bytes,
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
            "이미지 처리 요약(productId=%s, target=%s, input=%s, unique=%s, downloadOk=%s, downloadFail=%s, validationFail=%s, uploadOk=%s, uploadFail=%s, exceptions=%s, result=%s, validationFailures=%s)",
            product_id,
            stats["target_count"],
            stats["input_count"],
            stats["unique_candidates"],
            stats["download_ok"],
            stats["download_fail"],
            stats["validation_fail"],
            stats["upload_ok"],
            stats["upload_fail"],
            stats["exceptions"],
            len(processed_urls),
            stats["validation_failures"],
        )

        if (
            stats["download_fail"] > 0
            or stats["upload_fail"] > 0
            or stats["exceptions"] > 0
            or stats["validation_fail"] > 0
        ):
            logger.warning(
                "이미지 처리 경고(productId=%s, target=%s, input=%s, unique=%s, downloadOk=%s, downloadFail=%s, validationFail=%s, uploadOk=%s, uploadFail=%s, exceptions=%s, result=%s, validationFailures=%s)",
                product_id,
                stats["target_count"],
                stats["input_count"],
                stats["unique_candidates"],
                stats["download_ok"],
                stats["download_fail"],
                stats["validation_fail"],
                stats["upload_ok"],
                stats["upload_fail"],
                stats["exceptions"],
                len(processed_urls),
                stats["validation_failures"],
            )

        return processed_urls

    async def process_and_upload_images_async(
        self,
        image_urls: List[str],
        detail_html: str = "",
        product_id: str = "temp",
        max_images: int = 9,
        max_concurrent: int = 5,
    ) -> List[str]:
        """
        비동기 병렬 이미지 처리 파이프라인
        
        Args:
            image_urls: 이미지 URL 목록
            detail_html: 상세 HTML (추가 이미지 추출용)
            product_id: 상품 ID
            max_images: 최대 이미지 수
            max_concurrent: 동시 다운로드 수
        
        Returns:
            처리된 이미지 URL 목록
        """
        max_images = max(1, int(max_images))
        max_images = min(max_images, 9)
        
        candidates = image_urls[:]
        html_images = self.extract_images_from_html(detail_html, limit=20)
        if html_images:
            candidates.extend(html_images)

        # Deduplicate
        seen = set()
        unique_candidates = []
        for url in candidates:
            if url and url not in seen:
                unique_candidates.append(url)
                seen.add(url)

        logger.info(f"Processing {len(unique_candidates)} images for product {product_id} (async, max_concurrent={max_concurrent})...")
        
        # 이미지 처리 결과를 저장할 리스트
        processed_urls = []
        
        # 세마포어로 동시성 제어
        sem = asyncio.Semaphore(max_concurrent)
        
        async def process_single_image(url: str) -> Tuple[str, bytes | None, str | None]:
            async with sem:
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        image_bytes = await self._download_image_async(url, client)
                        
                        if not image_bytes:
                            return (url, None, "download_failed")
                        
                        validation = validate_image_bytes(image_bytes)
                        if not validation.ok:
                            logger.warning(
                                "이미지 검증 실패(url=%s, reason=%s, size=%s, width=%s, height=%s)",
                                url,
                                validation.reason,
                                validation.size_bytes,
                                validation.width,
                                validation.height,
                            )
                            return (url, None, f"validation_failed:{validation.reason}")
                        
                        # 업로드
                        new_url = storage_service.upload_image(
                            image_bytes,
                            path_prefix=f"market_processing/{product_id}"
                        )
                        
                        if new_url:
                            return (url, new_url, None)
                        else:
                            return (url, None, "upload_failed")
                            
                except Exception as e:
                    logger.error(f"이미지 처리 실패(url={url}): {e}")
                    return (url, None, f"exception:{str(e)}")
        
        # 병렬 처리
        tasks = [process_single_image(url) for url in unique_candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 결과 수집
        download_ok = 0
        download_fail = 0
        validation_fail = 0
        upload_ok = 0
        upload_fail = 0
        exceptions = 0
        validation_failures = {}
        
        for result in results:
            if isinstance(result, Exception):
                exceptions += 1
                continue
            
            url, new_url, error = result
            
            if error:
                if "download_failed" in error:
                    download_fail += 1
                elif "validation_failed" in error:
                    validation_fail += 1
                    reason = error.split(":", 1)[1] if ":" in error else "unknown"
                    validation_failures[reason] = validation_failures.get(reason, 0) + 1
                elif "upload_failed" in error:
                    upload_fail += 1
                elif "exception" in error:
                    exceptions += 1
                download_fail += 1
            else:
                download_ok += 1
                if new_url:
                    processed_urls.append(new_url)
                    upload_ok += 1
                else:
                    upload_fail += 1
            
            # 최대 이미지 수 도달 시 중단
            if len(processed_urls) >= max_images:
                break
        
        logger.info(
            "이미지 처리 요약(productId=%s, target=%s, input=%s, unique=%s, downloadOk=%s, downloadFail=%s, validationFail=%s, uploadOk=%s, uploadFail=%s, exceptions=%s, result=%s, validationFailures=%s)",
            product_id,
            max_images,
            len(candidates),
            len(unique_candidates),
            download_ok,
            download_fail,
            validation_fail,
            upload_ok,
            upload_fail,
            exceptions,
            len(processed_urls),
            validation_failures,
        )

        if download_fail > 0 or upload_fail > 0 or exceptions > 0 or validation_fail > 0:
            logger.warning(
                "이미지 처리 경고(productId=%s, target=%s, input=%s, unique=%s, downloadOk=%s, downloadFail=%s, validationFail=%s, uploadOk=%s, uploadFail=%s, exceptions=%s, result=%s, validationFailures=%s)",
                product_id,
                max_images,
                len(candidates),
                len(unique_candidates),
                download_ok,
                download_fail,
                validation_fail,
                upload_ok,
                upload_fail,
                exceptions,
                len(processed_urls),
                validation_failures,
            )

        return processed_urls

image_processing_service = ImageProcessingService()
