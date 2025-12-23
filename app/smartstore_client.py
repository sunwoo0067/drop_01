import logging
import time
import requests
import base64
import hmac
import hashlib
import bcrypt
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class SmartStoreClient:
    """
    네이버 커머스 API (스마트스토어) 클라이언트
    """
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://api.commerce.naver.com/external"
        self.token_url = "https://api.commerce.naver.com/external/v1/oauth2/token"
        
        self.access_token: Optional[str] = None
        self.expires_at: float = 0

    def _get_access_token(self) -> str:
        """
        OAuth2 Access Token을 발급받거나 갱신합니다.
        """
        if self.access_token and time.time() < self.expires_at - 60:
            return self.access_token

        timestamp = str(int(time.time() * 1000))
        
        # 네이버 커머스 API Signature 생성 (BCrypt 방식)
        # {client_id}_{timestamp} 문자열을 client_secret(salt)를 사용하여 bcrypt 해싱
        password = f"{self.client_id}_{timestamp}"
        hashed = bcrypt.hashpw(password.encode('utf-8'), self.client_secret.encode('utf-8'))
        signature = base64.b64encode(hashed).decode('utf-8')
        
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "timestamp": timestamp,
            "client_secret_sign": signature,
            "type": "SELF"
        }
        
        try:
            response = requests.post(self.token_url, data=payload)
            if response.status_code != 200:
                logger.error(f"Naver token request failed ({response.status_code}): {response.text}")
                response.raise_for_status()
                
            data = response.json()
            self.access_token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            self.expires_at = time.time() + expires_in
            
            logger.info("Successfully refreshed Naver SmartStore access token.")
            return self.access_token
        except Exception as e:
            logger.error(f"Failed to get Naver SmartStore access token: {e}")
            raise

    def _get_headers(self, multipart: bool = False) -> Dict[str, str]:
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}"
        }
        if not multipart:
            headers["Content-Type"] = "application/json"
        return headers

    def get_products(self, page: int = 1, size: int = 50) -> tuple[int, Dict[str, Any]]:
        """상품 목록 조회"""
        url = f"{self.base_url}/v2/products"
        params = {"page": page, "size": size}
        
        try:
            response = requests.get(url, headers=self._get_headers(), params=params)
            return response.status_code, response.json()
        except Exception as e:
            logger.error(f"SmartStore get_products error: {e}")
            return 500, {"message": str(e)}

    def create_product(self, payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
        """신규 상품 등록"""
        url = f"{self.base_url}/v2/products"
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            return response.status_code, response.json()
        except Exception as e:
            logger.error(f"SmartStore create_product error: {e}")
            return 500, {"message": str(e)}

    def update_product(self, origin_product_no: str, payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
        """상품 정보 수정"""
        url = f"{self.base_url}/v2/products/{origin_product_no}"
        try:
            response = requests.patch(url, headers=self._get_headers(), json=payload)
            return response.status_code, response.json()
        except Exception as e:
            logger.error(f"SmartStore update_product error: {e}")
            return 500, {"message": str(e)}

    def upload_images(self, image_urls: List[str]) -> List[str]:
        """이미지를 네이버 서버로 업로드하여 네이버 전용 URL 획득"""
        url = f"{self.base_url}/v1/product-images/upload"
        uploaded_urls = []
        
        for img_url in image_urls:
            try:
                # 1. 이미지 다운로드
                img_res = requests.get(img_url)
                if img_res.status_code != 200:
                    logger.error(f"Failed to download image: {img_url}")
                    continue
                
                # 2. 네이버 업로드
                files = {'imageFiles': ('image.jpg', img_res.content, 'image/jpeg')}
                response = requests.post(url, headers=self._get_headers(multipart=True), files=files)
                
                if response.status_code == 200:
                    results = response.json().get("images", [])
                    if results:
                        uploaded_urls.append(results[0].get("url"))
                else:
                    logger.error(f"Naver image upload failed: {response.text}")
            except Exception as e:
                logger.error(f"Error in upload_images: {e}")
                
        return uploaded_urls

    def delete_product(self, origin_product_no: str) -> tuple[int, Dict[str, Any]]:
        """상품 삭제 (또는 상태 변경)"""
        # 스마트스토어는 보통 삭제보다 '판매 중지' 또는 '삭제' 상태 변경 API를 사용
        url = f"{self.base_url}/v2/products/{origin_product_no}"
        try:
            response = requests.delete(url, headers=self._get_headers())
            return response.status_code, response.json()
        except Exception as e:
            logger.error(f"SmartStore delete_product error: {e}")
            return 500, {"message": str(e)}

    # 향후 등록(POST), 수정(PATCH) 등 추가 예정
