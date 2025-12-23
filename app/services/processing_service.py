import logging
import uuid
import json
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import Product, BenchmarkProduct, SupplierItemRaw
from app.settings import settings
from app.services.ai.agents.processing_agent import ProcessingAgent
from app.services.image_processing import image_processing_service
from app.services.detail_html_normalizer import normalize_ownerclan_html

logger = logging.getLogger(__name__)

class ProcessingService:
    def __init__(self, db: Session):
        self.db = db
        self.processing_agent = ProcessingAgent(db)

    def _name_only_processing(self) -> bool:
        return settings.product_processing_name_only

    async def process_product(self, product_id: uuid.UUID, min_images_required: int = 1) -> bool:
        """
        Orchestrates the processing of a single product using LangGraph ProcessingAgent.
        """
        try:
            logger.info(f"Starting LangGraph processing for product {product_id}...")
            
            product = self.db.scalars(select(Product).where(Product.id == product_id)).one_or_none()
            if not product:
                logger.error(f"Product {product_id} not found.") # Added this line back for better logging
                return False

            product.processing_status = "PROCESSING"
            self.db.commit()

            # 기본 정보 초기화 (에이전트 실패 대비)
            if not product.processed_name:
                product.processed_name = product.name
            
            # 데이터 추출
            raw_images: list[str] = []
            detail_html = ""
            if not self._name_only_processing():
                try:
                    if product.supplier_item_id:
                        raw_item = self.db.get(SupplierItemRaw, product.supplier_item_id)
                        raw = raw_item.raw if raw_item and isinstance(raw_item.raw, dict) else {}
                        
                        # 1. 메인 images 리스트 확인
                        images_val = raw.get("images")
                        if isinstance(images_val, str):
                            s = images_val.strip()
                            if s.startswith(("http://", "https://")):
                                raw_images.append(s)
                        elif isinstance(images_val, list):
                            for it in images_val[:30]:
                                if isinstance(it, str):
                                    s = it.strip()
                                    if s.startswith(("http://", "https://")) and s not in raw_images:
                                        raw_images.append(s)
                                elif isinstance(it, dict):
                                    u = it.get("url") or it.get("src")
                                    if isinstance(u, str):
                                        s = u.strip()
                                        if s.startswith(("http://", "https://")) and s not in raw_images:
                                            raw_images.append(s)
                        
                        # 2. thumbnail 필드 별도 확인 (중복 제거하며 추가)
                        thumb = raw.get("thumbnail") or raw.get("main_image")
                        if thumb and isinstance(thumb, str) and thumb.strip().startswith("http"):
                            t = thumb.strip()
                            if t not in raw_images:
                                raw_images.insert(0, t)

                        for key in ("detail_html", "detailHtml"):
                            val = raw.get(key)
                            if isinstance(val, str) and val.strip():
                                detail_html = val.strip()
                                break
                        if not detail_html:
                            val = raw.get("content") or raw.get("description")
                            if isinstance(val, str) and val.strip():
                                detail_html = val.strip()

                        if detail_html and raw_item and raw_item.supplier_code == "ownerclan":
                            detail_html = normalize_ownerclan_html(detail_html)
                            # 상세 HTML 즉시 반영 (에이전트 실패 시에도 정보 유지)
                            product.description = detail_html
                            self.db.commit()

                            # 이미지 추출 및 업로드
                            detail_html, _detail_imgs = image_processing_service.replace_html_image_urls(
                                detail_html,
                                product_id=str(product_id),
                                limit=20,
                            )
                            # 상세에서 추출된 이미지를 raw_images에 추가하여 에이전트/가공에 활용
                            if _detail_imgs:
                                for u in _detail_imgs:
                                    if u not in raw_images:
                                        raw_images.append(u)
                            
                            # 업로드된 이미지가 포함된 HTML로 한 번 더 업데이트
                            product.description = detail_html
                            self.db.commit()

                except Exception as e:
                    logger.warning(f"오너클랜 이미지 추출 실패(productId={product_id}): {e}")

            input_data = {
                "name": product.name,
                "brand": product.brand,
                "description": product.description,
                "images": raw_images,
                "detail_html": detail_html,
            }
            
            # 에이전트 실행
            try:
                result = await self.processing_agent.run(str(product_id), input_data)
                output = result.get("final_output", {})
                
                # 결과 반영
                if output.get("processed_name"):
                    product.processed_name = output.get("processed_name")
                if output.get("processed_keywords"):
                    product.processed_keywords = output.get("processed_keywords")
                if output.get("processed_image_urls"):
                    product.processed_image_urls = output.get("processed_image_urls")
            except Exception as e:
                logger.error(f"ProcessingAgent 실행 실패(productId={product_id}): {e}")
                # 에이전트 실패해도 추출된 이미지는 활용 시도
                if not self._name_only_processing() and (not product.processed_image_urls) and raw_images:
                    product.processed_image_urls = image_processing_service.process_and_upload_images(
                        raw_images, product_id=str(product_id)
                    )

            # 최종 상태 판정 유연화: 이름과 이미지가 최소 1장 이상이면 성공으로 간주
            has_name = bool(product.processed_name or product.name)
            if self._name_only_processing():
                has_images = True
            else:
                has_images = bool(product.processed_image_urls and len(product.processed_image_urls) >= max(1, int(min_images_required)))
            
            if has_name and has_images:
                product.processing_status = "COMPLETED"
            else:
                product.processing_status = "FAILED"
                logger.warning(f"상품 가공 불충분: has_name={has_name}, has_images={has_images} (count={len(product.processed_image_urls) if product.processed_image_urls else 0})")
                
            self.db.commit()
            logger.info(f"Successfully processed product {product_id}. Status: {product.processing_status}") # Added this line back for better logging
            return True
            
        except Exception as e:
            logger.error(f"Error processing product {product_id}: {e}")
            self.db.rollback()
            try:
                # Try to key status as failed
                product.processing_status = "FAILED"
                self.db.commit()
            except:
                pass
            return False

    async def process_pending_products(self, limit: int = 10, min_images_required: int = 1):
        """
        Finds pending products and processes them.
        """
        stmt = select(Product).where(Product.processing_status == "PENDING").limit(limit)
        products = self.db.scalars(stmt).all()
        
        count = 0
        for p in products:
            if await self.process_product(p.id, min_images_required=min_images_required):
                count += 1
        return count
