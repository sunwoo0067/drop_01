import logging
import uuid
import json
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import Product, BenchmarkProduct, SupplierItemRaw, SourcingCandidate
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
                logger.error(f"Product {product_id} not found.")
                return False

            product.processing_status = "PROCESSING"
            self.db.commit()

            # 기본 정보 초기화
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
                            product.description = detail_html
                            self.db.commit()

                            detail_html, _detail_imgs = image_processing_service.replace_html_image_urls(
                                detail_html,
                                product_id=str(product_id),
                                limit=20,
                            )
                            if _detail_imgs:
                                for u in _detail_imgs:
                                    if u not in raw_images:
                                        raw_images.append(u)
                            
                            product.description = detail_html
                            self.db.commit()
                except Exception as e:
                    logger.error(f"Error extracting data for product {product_id}: {e}")

            # 벤치마크 상품 정보 가져오기 시도
            benchmark_data = None
            if product.supplier_item_id:
                candidate = self.db.scalars(
                    select(SourcingCandidate).where(SourcingCandidate.supplier_item_id == str(product.supplier_item_id))
                ).first()
                
                if candidate and candidate.benchmark_product_id:
                    benchmark = self.db.get(BenchmarkProduct, candidate.benchmark_product_id)
                    if benchmark:
                        benchmark_data = {
                            "name": benchmark.name,
                            "visual_analysis": benchmark.visual_analysis,
                            "specs": benchmark.specs
                        }

            input_data = {
                "name": product.name,
                "brand": product.brand,
                "description": product.description,
                "images": raw_images,
                "detail_html": detail_html,
                "category": product.processed_category if hasattr(product, 'processed_category') else "일반",
                "target_market": "Coupang",
            }
            
            # 에이전트 실행
            try:
                result = await self.processing_agent.run(str(product_id), input_data, benchmark_data=benchmark_data)
                output = result.get("final_output", {})
                
                if output.get("processed_name"):
                    product.processed_name = output.get("processed_name")
                if output.get("processed_keywords"):
                    product.processed_keywords = output.get("processed_keywords")
                if output.get("processed_image_urls"):
                    product.processed_image_urls = output.get("processed_image_urls")
            except Exception as e:
                logger.error(f"ProcessingAgent 실행 실패(productId={product_id}): {e}")
                if not self._name_only_processing() and (not product.processed_image_urls) and raw_images:
                    product.processed_image_urls = image_processing_service.process_and_upload_images(
                        raw_images, product_id=str(product_id)
                    )

            has_name = bool(product.processed_name or product.name)
            if self._name_only_processing():
                has_images = True
            else:
                has_images = bool(product.processed_image_urls and len(product.processed_image_urls) >= max(1, int(min_images_required)))
            
            if has_name and has_images:
                product.processing_status = "COMPLETED"
            else:
                product.processing_status = "FAILED"
                
            self.db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error processing product {product_id}: {e}")
            self.db.rollback()
            try:
                product.processing_status = "FAILED"
                self.db.commit()
            except:
                pass
            return False

    async def process_pending_products(self, limit: int = 10, min_images_required: int = 1):
        stmt = select(Product).where(Product.processing_status == "PENDING").limit(limit)
        products = self.db.scalars(stmt).all()
        count = 0
        for p in products:
            if await self.process_product(p.id, min_images_required=min_images_required):
                count += 1
        return count

    def get_winning_products_for_processing(self, limit: int = 20) -> list[Product]:
        from sqlalchemy import func, desc
        from app.models import OrderItem
        stmt = (
            select(Product)
            .join(OrderItem, Product.id == OrderItem.product_id)
            .where(Product.processing_status.notin_(["PROCESSING", "PENDING_APPROVAL"]))
            .group_by(Product.id)
            .order_by(desc(func.count(OrderItem.id)), desc(func.sum(OrderItem.quantity)))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    async def process_winning_product(self, product_id: uuid.UUID) -> bool:
        from app.services.ai.service import AIService
        ai_service = AIService()
        try:
            product = self.db.get(Product, product_id)
            if not product:
                return False
            product.processing_status = "PROCESSING"
            self.db.commit()
            image_urls = product.processed_image_urls or []
            if image_urls:
                first_image_url = image_urls[0]
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(first_image_url)
                    image_data = resp.content
                features = ai_service.extract_visual_features(image_data)
                benchmark_data = None
                if product.benchmark_product_id:
                    benchmark = self.db.get(BenchmarkProduct, product.benchmark_product_id)
                    if benchmark:
                        benchmark_data = {
                            "visual_analysis": benchmark.visual_analysis,
                            "specs": benchmark.specs
                        }
                prompts = ai_service.generate_premium_image_prompt(features, benchmark_data)
                logger.info(f"Generated Premium Prompts for {product.name}: {prompts}")
                product.processing_status = "PENDING_APPROVAL"
                self.db.commit()
                return True
            product.processing_status = "FAILED"
            self.db.commit()
            return False
        except Exception as e:
            logger.error(f"Error in premium processing for product {product_id}: {e}")
            self.db.rollback()
            return False
