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
                "target_market": "Coupang", # Default
            }
            
            # 에이전트 실행
            try:
                # benchmark_data를 초기 상태에 포함하여 전달
                initial_state_overrides = {"benchmark_data": benchmark_data}
                
                # 에이전트 run 메서드가 추가 인자를 받는지 확인 후 수정 필요할 수 있음. 
                # 현재 run은 (product_id, input_data)만 받으므로, Agent 클래스 내부 run을 수정하거나 
                # input_data에 benchmark_data를 넣는 방식으로 우회 (여기서는 run 내부 initial_state 구성을 참고하여 처리)
                
                result = await self.processing_agent.run(str(product_id), input_data, benchmark_data=benchmark_data)
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

    def get_winning_products_for_processing(self, limit: int = 20) -> list[Product]:
        """
        판매 실적이 있는 상품 중 아직 프리미엄 가공이 되지 않은 상품을 우선적으로 선정합니다.
        """
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
        """
        판매 실적이 좋은 상품에 대해 VLM 분석 및 프리미엄 이미지 생성을 위한 프롬프트를 구성하고
        PENDING_APPROVAL 상태로 전환합니다.
        """
        from app.services.ai.service import AIService
        ai_service = AIService()

        try:
            product = self.db.get(Product, product_id)
            if not product:
                return False

            product.processing_status = "PROCESSING"
            self.db.commit()

            # 1. 원본 이미지 데이터 획득 (첫 번째 이미지를 분석 대상)
            image_urls = product.processed_image_urls or []
            if not image_urls:
                 from app.services.image_processing import image_processing_service
                 # Fallback to description images if processed ones are missing
                 # (Implementation omitted for brevity, assuming product has images)
                 pass

            if image_urls:
                first_image_url = image_urls[0]
                # 2. VLM 특징 추출
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(first_image_url)
                    image_data = resp.content

                features = ai_service.extract_visual_features(image_data)
                
                # 3. 벤치마킹 데이터 확인
                benchmark_data = None
                if product.benchmark_product_id:
                    benchmark = self.db.get(BenchmarkProduct, product.benchmark_product_id)
                    if benchmark:
                        benchmark_data = {
                            "visual_analysis": benchmark.visual_analysis,
                            "specs": benchmark.specs
                        }

                # 4. SD 프롬프트 생성
                prompts = ai_service.generate_premium_image_prompt(features, benchmark_data)
                
                # 5. 결과 저장 및 상태 업데이트
                # Note: 실제 이미지 생성은 별도 워커나 ComfyUI API 연동이 필요함
                # 여기서는 프롬프트 결과와 분석 데이터를 상품 메타데이터(description 등)에 임시 기록하거나 로깅
                logger.info(f"Generated Premium Prompts for {product.name}: {prompts}")
                
                # 가상의 고품질 이미지 생성 로직 (Placeholder)
                # product.processed_image_urls.append(generated_premium_url)

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
