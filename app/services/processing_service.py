import logging
import uuid
import asyncio
import json
from functools import lru_cache
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import Product, BenchmarkProduct, SupplierItemRaw, SourcingCandidate
from app.settings import settings
from app.services.ai.agents.processing_agent import ProcessingAgent
from app.services.image_processing import image_processing_service
from app.services.detail_html_normalizer import normalize_ownerclan_html
from app.services.processing.processing_autonomy_guard import ProcessingAutonomyGuard

logger = logging.getLogger(__name__)

# Few-shot 예제 캐시 (TTL 5분)
_few_shot_cache = {"data": None, "timestamp": 0}
_FEW_SHOT_CACHE_TTL = 300  # 5분

class ProcessingService:
    def __init__(self, db: Session):
        self.db = db
        self.processing_agent = ProcessingAgent(db)
        self.autonomy_guard = ProcessingAutonomyGuard(db)

    def _name_only_processing(self) -> bool:
        return settings.product_processing_name_only

    def _get_cached_few_shot_examples(self, category: str = "일반", limit: int = 3) -> list[dict]:
        """
        캐시된 Few-shot 예제를 반환합니다.
        """
        import time
        current_time = time.time()
        
        # 캐시 유효성 확인
        if _few_shot_cache["data"] is not None and (current_time - _few_shot_cache["timestamp"]) < _FEW_SHOT_CACHE_TTL:
            return _few_shot_cache["data"]
        
        # 캐시 갱신
        try:
            from app.models import Product
            stmt = (
                select(Product.name, Product.processed_name)
                .where(Product.processing_status == "COMPLETED")
                .limit(limit)
            )
            results = self.db.execute(stmt).all()
            examples = [
                {"original": r[0], "processed": r[1]}
                for r in results
                if r[0] and r[1]
            ]
            _few_shot_cache["data"] = examples
            _few_shot_cache["timestamp"] = current_time
            return examples
        except Exception as e:
            logger.warning(f"Failed to fetch few-shot examples: {e}")
            return []

    async def process_product(self, product_id: uuid.UUID, min_images_required: int = 1) -> bool:
        """
        Orchestrates the processing of a single product using LangGraph ProcessingAgent.
        """
        try:
            logger.info(f"LangGraph 상품 가공 시작 (상품 ID: {product_id})...")

            product = self.db.scalars(select(Product).where(Product.id == product_id)).one_or_none()
            if not product:
                logger.error(f"상품을 찾을 수 없습니다 (상품 ID: {product_id})")
                return False

            product.processing_status = "PROCESSING"
            self.db.commit()

            # 자율성 체크: 상품명 최적화 자동 실행 여부 확인
            can_auto_process, reasons, tier = self.autonomy_guard.check_processing_autonomy(
                product, 
                "NAME",
                metadata={"vendor": "ownerclan", "channel": "COUPANG"}
            )
            
            if not can_auto_process:
                logger.info(f"상품명 최적화가 자율성 정책에 의해 승인 대기 (상품 ID: {product_id}, 사유: {reasons})")
                product.processing_status = "PENDING_APPROVAL"
                product.last_processing_type = "NAME"
                self.db.commit()
                return True

            # 기본 정보 초기화
            if not product.processed_name:
                product.processed_name = product.name
            
            # 데이터 추출
            raw_images: list[str] = []
            detail_html = ""
            name_only = self._name_only_processing()
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

                    if not name_only:
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
                            # 중간 commit 제거 - 최종 commit에서 한 번에 처리

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
                            # 중간 commit 제거 - 최종 commit에서 한 번에 처리
            except Exception as e:
                logger.error(f"상품 데이터 추출 실패 (상품 ID: {product_id}): {e}")

            # 벤치마크 상품 정보 가져오기 시도
            benchmark_data = None
            benchmark = None
            if product.supplier_item_id:
                # supplier_item_id (UUID) -> SupplierItemRaw (item_code) -> SourcingCandidate (supplier_item_id)
                raw_item = self.db.get(SupplierItemRaw, product.supplier_item_id)
                if raw_item and raw_item.item_code:
                    candidate = self.db.scalars(
                        select(SourcingCandidate).where(SourcingCandidate.supplier_item_id == raw_item.item_code)
                    ).first()
                else:
                    candidate = None
                
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
            
            # 에이전트 실행 (name-only 모드에서는 외부 AI 호출 스킵)
            if name_only:
                if not product.processed_name:
                    product.processed_name = product.name
                if product.processed_keywords is None:
                    product.processed_keywords = []
            else:
                try:
                    result = await self.processing_agent.run(str(product_id), input_data, benchmark_data=benchmark_data)
                    # Handle dictionary or object response
                    if hasattr(result, "get"):
                        output = result.get("final_output", {})
                    else:
                        output = getattr(result, "final_output", {})
                    
                    if output.get("processed_name"):
                        product.processed_name = output.get("processed_name")
                    if output.get("processed_keywords"):
                        product.processed_keywords = output.get("processed_keywords")
                    if output.get("processed_image_urls"):
                        product.processed_image_urls = output.get("processed_image_urls")
                except Exception as e:
                    logger.error(f"ProcessingAgent 실행 실패 (상품 ID: {product_id}): {e}")
                    if not self._name_only_processing() and (not product.processed_image_urls) and raw_images:
                        # 비동기 이미지 처리 사용
                        product.processed_image_urls = await image_processing_service.process_and_upload_images_async(
                            raw_images, product_id=str(product_id)
                        )

            has_name = bool(product.processed_name or product.name)
            if name_only:
                has_images = len(raw_images) >= max(1, int(min_images_required))
            else:
                has_images = bool(product.processed_image_urls and len(product.processed_image_urls) >= max(1, int(min_images_required)))
            
            if has_name and has_images:
                product.processing_status = "COMPLETED"
            else:
                product.processing_status = "FAILED"
                
            self.db.commit()
            return True
            
        except Exception as e:
            logger.error(f"상품 가공 중 오류 발생 (상품 ID: {product_id}): {e}")
            self.db.rollback()
            try:
                product.processing_status = "FAILED"
                self.db.commit()
            except:
                pass
            return False

    async def process_pending_products(self, limit: int = 10, min_images_required: int = 1):
        # 대기 중인 상품 ID 목록만 먼저 가져옴 (세션 공유 최소화)
        stmt = select(Product.id).where(Product.processing_status == "PENDING").limit(limit)
        product_ids = self.db.scalars(stmt).all()
        
        if not product_ids:
            return 0

        from app.session_factory import session_factory
        
        # 병렬 처리를 위한 세마포어 (API 부하 조절)
        sem = asyncio.Semaphore(max(1, int(settings.processing_concurrent_limit)))
        
        async def _limited_process(p_id):
            async with sem:
                # 각 가공 테스크마다 독립된 DB 세션 생성하여 충돌 방지
                with session_factory() as tmp_db:
                    try:
                        # 새 세션을 사용하는 별도의 서비스 인스턴스 생성
                        scoped_service = ProcessingService(tmp_db)
                        return await scoped_service.process_product(p_id, min_images_required=min_images_required)
                    except Exception as e:
                        logger.error(f"범위 가공 중 오류 발생 (상품 ID: {p_id}): {e}")
                        return False
        
        tasks = [_limited_process(pid) for pid in product_ids]
        results = await asyncio.gather(*tasks)
        return sum(1 for r in results if r)

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
            
            # 자율성 체크: 프리미엄 이미지 생성 자동 실행 여부 확인
            can_auto_process, reasons, tier = self.autonomy_guard.check_processing_autonomy(
                product, 
                "PREMIUM_IMAGE",
                metadata={"vendor": "ownerclan", "channel": "COUPANG"}
            )
            
            if not can_auto_process:
                logger.info(f"프리미엄 이미지 생성이 자율성 정책에 의해 승인 대기 (상품 ID: {product_id}, 사유: {reasons})")
                product.processing_status = "PENDING_APPROVAL"
                product.last_processing_type = "PREMIUM_IMAGE"
                self.db.commit()
                return True
            
            image_urls = product.processed_image_urls or []
            if image_urls:
                first_image_url = image_urls[0]
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(first_image_url)
                    image_data = resp.content
                features = await ai_service.extract_visual_features(image_data)
                benchmark_data = None
                benchmark = None
                if product.benchmark_product_id:
                    benchmark = self.db.get(BenchmarkProduct, product.benchmark_product_id)
                    if benchmark:
                        benchmark_data = {
                            "visual_analysis": benchmark.visual_analysis,
                            "specs": benchmark.specs
                        }
                prompts = await ai_service.generate_premium_image_prompt(features, benchmark_data)
                logger.info(f"프리미엄 프롬프트 생성 완료 ({product.name}): {prompts}")
                
                positive_prompt = prompts.get("positive_prompt")
                negative_prompt = prompts.get("negative_prompt", "")
                
                if positive_prompt:
                    logger.info(f"프리미엄 이미지 생성 시작 (상품 ID: {product.id})...")
                    image_bytes = await ai_service.generate_image(
                        prompt=positive_prompt,
                        negative_prompt=negative_prompt,
                        provider="sd"
                    )
                    
                    if image_bytes:
                        # 이미지 업로드 (동기 I/O이므로 별도 스레드에서 실행)
                        from app.services.storage_service import storage_service
                        new_image_url = await asyncio.to_thread(
                            storage_service.upload_image,
                            image_bytes,
                            path_prefix=f"premium_assets/{product.id}"
                        )
                        
                        if new_image_url:
                            logger.info(f"프리미엄 이미지 업로드 완료: {new_image_url}")
                            # 대표 이미지 목록 앞에 추가
                            current_images = product.processed_image_urls or []
                            product.processed_image_urls = [new_image_url] + current_images
                            
                            # 상세페이지 상단에 프리미엄 헤더 이미지로 삽입
                            if product.description:
                                premium_html = f'<div style="text-align:center; margin-bottom:20px;"><img src="{new_image_url}" style="max-width:100%; border-radius:8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);"></div>'
                                product.description = premium_html + product.description

                product.processing_status = "PENDING_APPROVAL"
                self.db.commit()
                return True
            product.processing_status = "FAILED"
            self.db.commit()
            return False
        except Exception as e:
            logger.error(f"프리미엄 가공 중 오류 발생 (상품 ID: {product_id}): {e}")
            self.db.rollback()
            return False
