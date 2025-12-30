import logging
import uuid
import asyncio
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SourcingCandidate, BenchmarkProduct, SupplierItemRaw, Product, SupplierSyncJob, ProductOption
from app.services.ai.agents.sourcing_agent import SourcingAgent
from app.embedding_service import EmbeddingService
from app.normalization import clean_product_name
from app.settings import settings
from app.services.analytics.coupang_policy import CoupangSourcingPolicyService

logger = logging.getLogger(__name__)

FORBIDDEN_KEYWORDS = [
    "배터리", "리튬", "lithium", "battery",
    "전기차", "electric vehicle", "ev",
    "킥보드", "kickboard", "스쿠터", "scooter",
    "전동", "motorized",
    "성인용품", "adult",
]

class SourcingService:
    def __init__(self, db: Session):
        self.db = db
        self.sourcing_agent = SourcingAgent(db)
        self.embedding_service = EmbeddingService()
        self._ai_semaphore = asyncio.Semaphore(50) # 1 -> 50 상향

    async def execute_benchmark_sourcing(self, benchmark_id: uuid.UUID):
        """
        Execute high-level sourcing using LangGraph agent.
        """
        benchmark = (
            self.db.execute(select(BenchmarkProduct).where(BenchmarkProduct.id == benchmark_id))
            .scalar_one_or_none()
        )
        if not benchmark:
            logger.error("Benchmark product %s not found", benchmark_id)
            return

        input_data = {
            "name": benchmark.name,
            "detail_html": benchmark.detail_html,
            "price": benchmark.price,
            "images": benchmark.image_urls or []
        }

        try:
            result_state = await self.sourcing_agent.run(str(benchmark_id), input_data)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Benchmark sourcing agent failed: %s", exc)
            return

        candidate_results = (result_state or {}).get("candidate_results") or []
        specs = (result_state or {}).get("specs")
        visual_analysis = (result_state or {}).get("visual_analysis")
        
        if not candidate_results:
            logger.warning("Benchmark sourcing agent returned no candidates for %s", benchmark_id)
            return

        for candidate_data in candidate_results:
            await self._create_candidate(
                candidate_data,
                strategy="BENCHMARK_AGENT",
                benchmark_id=benchmark.id,
                seasonal_score=candidate_data.get("seasonal_score"),
                spec_data=specs,
                thumbnail_url=candidate_data.get("thumbnail_url"),
                visual_analysis=visual_analysis,
                expert_match_score=candidate_data.get("expert_match_score"),
                expert_match_reason=candidate_data.get("expert_match_reason"),
            )
        
        logger.info(f"LangGraph Agent sourcing finished for {benchmark.name}")

    async def execute_keyword_sourcing(self, keyword: str, limit: int = 100):
        """
        Standard keyword-based sourcing.
        """
        logger.info(f"Executing keyword sourcing for: {keyword}")
        
        # 1. Coupang Sourcing Policy Check (Option C)
        policy = CoupangSourcingPolicyService.evaluate_keyword_policy(self.db, keyword)
        decision = CoupangSourcingPolicyService.get_action_from_policy(policy)
        
        logger.info(
            "[SOURCING_POLICY] keyword=\"%s\" grade=%s score=%s mode=%s action=%s (Limit: %d)",
            keyword, decision["grade"], decision["score"], decision["mode"], decision["action"], decision["max_items"]
        )
        
        # Override limit based on policy
        final_limit = min(limit, decision["max_items"])
        
        if decision["action"] == "skip_coupang" and settings.coupang_sourcing_policy_mode != "shadow":
            logger.warning("Coupang sourcing skipped for keyword: %s (BLOCK)", keyword)
            # 네이버 전용으로 진행하거나 아예 중단 선택 가능. 여기서는 수량 0으로 중단 효과.
            if not decision["allowed_markets"] or "coupang" not in decision["allowed_markets"]:
                # 만약 네이버만 허용된다면 네이버용으로 소싱 진행 가능하나, 
                # 현재 시스템은 소싱 후 등록 단계에서 계정별로 처리하므로 
                # 여기서는 수량 제한으로 제어합니다.
                pass

        from app.ownerclan_client import OwnerClanClient
        from app.models import SupplierAccount
        acc = self.db.execute(
            select(SupplierAccount).where(SupplierAccount.supplier_code == "ownerclan").where(SupplierAccount.is_active == True)
        ).scalars().first()
        
        client = OwnerClanClient(
            auth_url=settings.ownerclan_auth_url,
            api_base_url=settings.ownerclan_api_base_url,
            graphql_url=settings.ownerclan_graphql_url,
            access_token=acc.access_token if acc else None
        )
        # 정책에 따른 수량 제한 적용
        status, data = client.get_products(keyword=keyword, limit=final_limit)
        if status != 200:
            logger.error(f"Failed to fetch products for keyword: {keyword}")
            return

        items = data.get("data", {}).get("items") or data.get("items") or []
        for item in items:
            await self._create_candidate(
                item, 
                strategy="KEYWORD_SEARCH",
                policy_decision=decision # 정책 결정 사항 전달
            )

    async def execute_trend_sourcing(self):
        """
        Scans trends and triggers expanded sourcing.
        """
        from app.benchmark.collectors.naver_shopping import NaverShoppingBenchmarkCollector
        collector = NaverShoppingBenchmarkCollector()
        trending_keywords = await collector.collect_trending_keywords()
        logger.info(f"Captured {len(trending_keywords)} trending keywords: {trending_keywords}")
        
        for kw in trending_keywords:
            await self.execute_expanded_sourcing(kw)

    async def execute_expanded_sourcing(self, keyword: str):
        """
        Expands keywords via AI and sources each.
        """
        logger.info(f"Expanding keyword: {keyword}")
        from app.services.ai.service import AIService
        ai = AIService()
        expanded = await ai.expand_keywords(keyword)
        logger.info(f"Expanded '{keyword}' into: {expanded}")
        
        # Source original keyword
        await self.execute_keyword_sourcing(keyword)
        
        # Source expanded keywords
        for ekw in expanded:
            await self.execute_keyword_sourcing(ekw)

    def _to_int(self, value: any) -> int:
        if value is None: return 0
        try:
            if isinstance(value, str):
                import re
                value = re.sub(r'[^\d]', '', value)
            return int(value)
        except:
            return 0

    async def _create_candidate(
        self,
        item: dict,
        strategy: str,
        benchmark_id: uuid.UUID | None = None,
        seasonal_score: float | None = None,
        margin_score: float | None = None,
        spec_data: dict | None = None,
        thumbnail_url: str | None = None,
        visual_analysis: str | None = None,
        expert_match_score: float | None = None,
        expert_match_reason: str | None = None,
        policy_decision: dict | None = None,
    ):
        async with self._ai_semaphore:
            return await self._execute_create_candidate(
                item, strategy, benchmark_id, seasonal_score, margin_score, spec_data, thumbnail_url, visual_analysis, expert_match_score, expert_match_reason, policy_decision
            )

    async def _execute_create_candidate(
        self,
        item: dict,
        strategy: str,
        benchmark_id: uuid.UUID | None = None,
        seasonal_score: float | None = None,
        margin_score: float | None = None,
        spec_data: dict | None = None,
        thumbnail_url: str | None = None,
        visual_analysis: str | None = None,
        expert_match_score: float | None = None,
        expert_match_reason: str | None = None,
        policy_decision: dict | None = None,
    ):
        supplier_id = (
            item.get("item_code")
            or item.get("itemCode")
            or item.get("item_id")
            or item.get("id")
            or item.get("item")
        )
        if supplier_id is None:
            return

        name = item.get("item_name") or item.get("name") or item.get("itemName") or "Unknown"
        
        # 0. Keyword filtering (Pre-emptive)
        for kw in FORBIDDEN_KEYWORDS:
            if kw.lower() in name.lower():
                logger.info("Skipping forbidden product candidate: %s (keyword: %s)", name, kw)
                return

        exists = (
            self.db.execute(
                select(SourcingCandidate)
                .where(SourcingCandidate.supplier_code == "ownerclan")
                .where(SourcingCandidate.supplier_item_id == str(supplier_id))
            )
            .scalars()
            .first()
        )
        if exists:
            # Update existing candidate with new analysis if it was bulk collected
            if exists.source_strategy == "BULK_COLLECT" and strategy == "BENCHMARK_AGENT":
                exists.source_strategy = strategy
                exists.benchmark_product_id = benchmark_id
                exists.visual_analysis = visual_analysis
                exists.spec_data = spec_data
                exists.final_score = expert_match_score
                self.db.commit()
            return

        # Ensure raw data is in SupplierItemRaw for the product pipeline
        raw_entry = self.db.execute(
            select(SupplierItemRaw)
            .where(SupplierItemRaw.supplier_code == "ownerclan")
            .where(SupplierItemRaw.item_code == str(supplier_id))
        ).scalar_one_or_none()
        
        if not raw_entry:
            raw_entry = SupplierItemRaw(
                supplier_code="ownerclan",
                item_code=str(supplier_id),
                item_key=item.get("item_key") or item.get("itemKey"),
                item_id=str(supplier_id),
                raw=item
            )
            self.db.add(raw_entry)
            self.db.flush() # Get ID
        
        name = item.get("item_name") or item.get("name") or item.get("itemName") or "Unknown"
        supply_price = self._to_int(item.get("supply_price") or item.get("supplyPrice") or item.get("fixedPrice") or item.get("price")) or 0

        final_thumbnail_url = thumbnail_url
        if not final_thumbnail_url:
            images = item.get("images")
            if isinstance(images, list) and images:
                final_thumbnail_url = images[0]

        embedding = None
        similarity_score = None
        benchmark = None
        if benchmark_id:
            benchmark = (
                self.db.execute(select(BenchmarkProduct).where(BenchmarkProduct.id == benchmark_id))
                .scalar_one_or_none()
            )
            if benchmark:
                candidate_text = f"{name} {item.get('detail_html', '')}".strip()
                
                # 1. Similarity Score (Embedding Cosine Similarity)
                if benchmark.embedding is not None:
                    candidate_images = [final_thumbnail_url] if final_thumbnail_url else []
                    embedding = await self.embedding_service.generate_rich_embedding(candidate_text, image_urls=candidate_images)
                    if embedding:
                        similarity_score = self.embedding_service.compute_similarity(benchmark.embedding, embedding)

                # 2. Solution Matching (Pain Point Gap Analysis)
                if benchmark.pain_points:
                    # Boost similarity_score if description contains "solutions" to pain points
                    # e.g. "noisy" in pain_points -> "silent" in candidate_text
                    # This is a simple heuristic, ideally done via AI
                    for pp in benchmark.pain_points:
                        if "noise" in pp.lower() or "소음" in pp:
                            if any(x in candidate_text for x in ["저소음", "무소음", "silent", "quiet"]):
                                similarity_score = min(1.0, (similarity_score or 0.5) + 0.1)

        # 3. Final Multi-Factor Weighted Scoring
        # Profitability (40%)
        profit_score = 0.5 # Default middle
        if supply_price > 0 and (benchmark_price := (benchmark.price if benchmark else 0)) > 0:
            margin_rate = (benchmark_price - supply_price) / benchmark_price
            if margin_rate >= 0.15: profit_score = 1.0 # 20% -> 15% 완화
            elif margin_rate > 0: profit_score = margin_rate / 0.15
        
        # Seasonality (30%)
        # already provided as seasonal_score arg, or default to 0.5
        s_score = seasonal_score if seasonal_score is not None else 0.5
        
        # Competition (20%) - Placeholder (Default high if unknown)
        comp_score = 1.0 
        
        # Quality (10%) - Heuristic based on rating or description quality
        # Minimum 0.3 for items having any html content
        raw_html = item.get("detail_html", "") or ""
        quality_score = max(0.3, min(1.0, len(raw_html) / 2000.0)) # threshold 완화

        # Total Calculation
        final_ws = (profit_score * 0.4) + (s_score * 0.3) + (comp_score * 0.2) + (quality_score * 0.1)
        # Normalize to 0-100 for storage if desired, or keep as 0-1
        # User specified "85점 이상", so let's use 0-100
        final_score_val = final_ws * 100.0
        
        # If expert match score exists (from agent), average it in or use it to override
        if expert_match_score is not None:
            final_score_val = (final_score_val + (expert_match_score * 100.0)) / 2.0

        # 4. Policy Boost (Amplification): 검증된 등급에 가산점 부여
        if policy_decision:
            grade = policy_decision.get("grade")
            if grade == "CORE":
                final_score_val += 10.0
                logger.info(f"Policy Boost: CORE +10 (New Score: {final_score_val:.1f})")
            elif grade in ("TRY", "RESEARCH"):
                # RESEARCH도 신규모험 촉진을 위해 TRY와 동일하게 가산점 부여 (사용자 제안 반영)
                final_score_val += 5.0
                logger.info(f"Policy Boost: {grade} +5 (New Score: {final_score_val:.1f})")
            elif grade == "BLOCK":
                final_score_val -= 50.0 # BLOCK은 자동 승인 방지
                logger.info(f"Policy Penalty: BLOCK -50 (New Score: {final_score_val:.1f})")

        final_score_val = max(0.0, min(100.0, final_score_val))

        candidate = SourcingCandidate(
            supplier_code="ownerclan",
            supplier_item_id=str(supplier_id),
            name=str(name),
            supply_price=int(supply_price),
            source_strategy=strategy,
            benchmark_product_id=benchmark_id,
            seasonal_score=seasonal_score,
            margin_score=margin_score,
            similarity_score=similarity_score,
            embedding=embedding,
            spec_data=spec_data,
            thumbnail_url=final_thumbnail_url,
            visual_analysis=visual_analysis,
            final_score=final_score_val,
            sourcing_policy=policy_decision,
            status="PENDING",
        )

        self.db.add(candidate)
        self.db.commit()
        logger.info("Created candidate: %s (Final Score=%.2f)", candidate.name, final_score_val)

        # Auto-Approval Pipeline
        if final_score_val >= 85:
            logger.info(f"Auto-approving high score candidate: {candidate.name} ({final_score_val})")
            await self.approve_candidate(candidate.id)

    async def approve_candidate(self, candidate_id: uuid.UUID):
        """
        Promotes a candidate to a real Product and triggers AI SEO/Image pipeline.
        """
        candidate = self.db.get(SourcingCandidate, candidate_id)
        if not candidate:
            return

        # 이미 Product가 생성되었는지 확인 (중복 생성 방지)
        existing_product = self.db.execute(
            select(Product).where(Product.supplier_item_id.in_(
                select(SupplierItemRaw.id).where(SupplierItemRaw.item_code == candidate.supplier_item_id)
            ))
        ).scalars().first()
        
        if existing_product:
            candidate.status = "APPROVED" # 상태만 보정
            self.db.commit()
            return

        candidate.status = "APPROVED"
        self.db.commit()

        # 1. Create Product
        from app.services.ai.service import AIService
        from app.ownerclan_client import OwnerClanClient
        ai = AIService()
        
        # 1.1 공급처로부터 최신 상세 정보(옵션 포함) 다시 가져오기
        from app.models import SupplierAccount
        acc = self.db.execute(
            select(SupplierAccount).where(SupplierAccount.supplier_code == "ownerclan").where(SupplierAccount.is_active == True)
        ).scalars().first()
        
        client = OwnerClanClient(
            auth_url=settings.ownerclan_auth_url,
            api_base_url=settings.ownerclan_api_base_url,
            graphql_url=settings.ownerclan_graphql_url,
            access_token=acc.access_token if acc else None
        )
        
        logger.info(f"Fetching full details for {candidate.supplier_item_id} from OwnerClan...")
        status, detail_data = client.get_product(candidate.supplier_item_id)
        item_full_data = detail_data.get("data") if isinstance(detail_data, dict) else detail_data
        
        if status == 404:
            logger.error(f"Product {candidate.supplier_item_id} not found on supplier. Rejecting candidate.")
            candidate.status = "REJECTED"
            self.db.commit()
            return

        if status != 200 or not item_full_data:
            logger.warning(f"Failed to fetch full details for {candidate.supplier_item_id}. Using candidate cache.")
            item_full_data = {}
        
        # Find or update raw record
        raw_entry = self.db.execute(
            select(SupplierItemRaw)
            .where(SupplierItemRaw.supplier_code == candidate.supplier_code)
            .where(SupplierItemRaw.item_code == candidate.supplier_item_id)
        ).scalar_one_or_none()
        
        if not raw_entry:
            raw_entry = SupplierItemRaw(
                supplier_code=candidate.supplier_code,
                item_code=candidate.supplier_item_id,
                raw=item_full_data if item_full_data else {"name": candidate.name, "price": candidate.supply_price}
            )
            self.db.add(raw_entry)
            self.db.flush()
        elif item_full_data:
            # 최신 데이터로 업데이트 (옵션 정보 확보)
            raw_entry.raw = item_full_data
            self.db.flush()

        # Clean original name
        cleaned_name = clean_product_name(candidate.name)
        
        # Optimize SEO
        seo = await ai.optimize_seo(cleaned_name, candidate.seo_keywords or [], context=candidate.visual_analysis)
        processed_name = seo.get("title") or cleaned_name
        processed_keywords = seo.get("tags") or candidate.seo_keywords
        
        from app.services.market_targeting import resolve_trade_flags_from_raw
        parallel_imported, overseas_purchased = resolve_trade_flags_from_raw(item_full_data)

        product = Product(
            supplier_item_id=raw_entry.id, # Link to raw record
            name=cleaned_name,
            processed_name=processed_name,
            processed_keywords=processed_keywords,
            cost_price=candidate.supply_price,
            selling_price=int(candidate.supply_price * 1.3), # Default 30% margin
            status="DRAFT",
            processing_status="PENDING",
            processed_image_urls=[candidate.thumbnail_url] if candidate.thumbnail_url else [],
            description=item_full_data.get("detail_html") or item_full_data.get("content"),
            coupang_parallel_imported=parallel_imported,
            coupang_overseas_purchased=overseas_purchased,
            sourcing_policy=candidate.sourcing_policy,
        )
        self.db.add(product)
        self.db.flush() # ID 확보
        
        # 1.2 Parse and save options
        # 오너클랜은 보통 'options' 또는 'option_list'에 정보를 담음
        options_data = item_full_data.get("options") or item_full_data.get("option_list") or []
        
        if options_data:
            for opt in options_data:
                # 오너클랜 옵션 구조: {'optionAttributes': [{'name': '색상', 'value': '블랙'}], 'price': 10000, 'quantity': 50, 'key': '...'}
                attrs = opt.get("optionAttributes") or opt.get("option_attributes") or []
                if not attrs and opt.get("name"):
                     # 단순 텍스트 옵션 처리
                     opt_name = "옵션"
                     opt_value = opt.get("name")
                else:
                    opt_name = "/".join([str(a.get("name", "")) for a in attrs if a.get("name")]) or "옵션"
                    opt_value = "/".join([str(a.get("value", "")) for a in attrs if a.get("value")]) or "기본"
                
                # 가격 정보 (차액인지 절대값인지 주의, 오너클랜 API는 보통 개별 아이템 가격)
                opt_price = self._to_int(opt.get("price") or opt.get("supply_price")) or product.cost_price
                
                new_opt = ProductOption(
                    product_id=product.id,
                    option_name=opt_name,
                    option_value=opt_value,
                    cost_price=opt_price,
                    selling_price=int(opt_price * 1.3), # 동일 마진 적용
                    stock_quantity=self._to_int(opt.get("quantity") or opt.get("stock")) or 999,
                    external_option_key=str(opt.get("key") or opt.get("option_code") or "")
                )
                self.db.add(new_opt)
        else:
            # 옵션이 없는 경우 기본 옵션 하나 생성
            default_opt = ProductOption(
                product_id=product.id,
                option_name="기본",
                option_value="단품",
                cost_price=product.cost_price,
                selling_price=product.selling_price,
                stock_quantity=999, # 기본값
                external_option_key="DEFAULT"
            )
            self.db.add(default_opt)

        self.db.commit()
        logger.info(f"Promoted candidate to Product with {len(product.options) if product.options else 0} options: {product.name} (ID: {product.id})")
        
        # 2. Trigger Image Processing (Placeholder for background task)
        # In a real app, this would be a Celery task or BackgroundTask
        # self.image_processing_service.trigger(product.id)

    def find_similar_items_in_raw(self, embedding: List[float], limit: int = 10) -> List[SourcingCandidate]:
        stmt = (
            select(SourcingCandidate)
            .order_by(SourcingCandidate.embedding.cosine_distance(embedding))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    async def trigger_full_supplier_sync(self):
        """
        Schedules a background sync job for ALL products from OwnerClan.
        Checks if a job is already in progress to avoid duplicates.
        """
        from app.ownerclan_sync import start_background_ownerclan_job
        from app.session_factory import session_factory
        
        # Check for existing active jobs
        existing_job = (
            self.db.execute(
                select(SupplierSyncJob)
                .where(SupplierSyncJob.supplier_code == "ownerclan")
                .where(SupplierSyncJob.job_type == "ownerclan_items_raw")
                .where(SupplierSyncJob.status.in_(["pending", "running"]))
            )
            .scalars()
            .first()
        )
        
        if existing_job:
            logger.info(f"Full supplier sync already in progress (Job ID: {existing_job.id}). Skipping trigger.")
            return existing_job.id

        logger.info("Triggering full supplier sync job for OwnerClan...")
        # Create a new job record for tracking
        job = SupplierSyncJob(
            supplier_code="ownerclan",
            job_type="ownerclan_items_raw",
            status="pending",
            params={"datePreset": "all"}
        )
        self.db.add(job)
        self.db.commit()
        
        # Start in background thread
        start_background_ownerclan_job(session_factory, job.id)
        return job.id

    def import_from_raw(self, limit: int = 1000) -> int:
        """
        Converts un-processed SupplierItemRaw records into SourcingCandidates.
        This allows items collected via background sync to enter the pipeline.
        """
        
        # Find raw items that don't have a corresponding candidate yet
        # Using a subquery for 'not exists' is efficient
        subq = select(SourcingCandidate.supplier_item_id).where(SourcingCandidate.supplier_code == "ownerclan")
        stmt = (
            select(SupplierItemRaw)
            .where(SupplierItemRaw.supplier_code == "ownerclan")
            .where(SupplierItemRaw.item_code.notin_(subq))
            .limit(limit)
        )
        
        raw_items = self.db.execute(stmt).scalars().all()
        count = 0
        
        for raw in raw_items:
            # Create a candidate for each raw item
            # We use a simple 'BULK_COLLECT' strategy for these
            item_data = raw.raw if isinstance(raw.raw, dict) else {}
            
            # Simple metadata extraction
            name = item_data.get("name") or "Unnamed Product"
            price = item_data.get("price") or item_data.get("fixedPrice") or 0
            thumbnail_url = None
            images = item_data.get("images")
            if isinstance(images, list) and images:
                thumbnail_url = images[0]
            elif isinstance(images, str):
                candidate = images.strip()
                if candidate.startswith(("http://", "https://")):
                    thumbnail_url = candidate
            
            # Basic validation
            if not name or price <= 0:
                continue
                
            # Keyword filtering
            is_forbidden = False
            for kw in FORBIDDEN_KEYWORDS:
                if kw.lower() in str(name).lower():
                    logger.info("Skipping forbidden product candidate from raw: %s (keyword: %s)", name, kw)
                    is_forbidden = True
                    break
            if is_forbidden:
                continue
                
            candidate = SourcingCandidate(
                supplier_code="ownerclan",
                supplier_item_id=str(raw.item_code),
                name=str(name),
                supply_price=int(price),
                thumbnail_url=thumbnail_url,
                source_strategy="BULK_COLLECT",
                status="PENDING",
                final_score=50.0 # Default score for bulk collected items
            )
            self.db.add(candidate)
            count += 1
            
        self.db.commit()
        if count > 0:
            logger.info(f"Imported {count} items from raw storage to sourcing candidates.")
        return count
