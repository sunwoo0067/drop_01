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

logger = logging.getLogger(__name__)

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
        from app.ownerclan_client import OwnerClanClient
        # Use ownerclan client to search
        client = OwnerClanClient(
            auth_url=settings.ownerclan_auth_url,
            api_base_url=settings.ownerclan_api_base_url,
            graphql_url=settings.ownerclan_graphql_url
        )
        status, data = client.get_products(keyword=keyword, limit=limit)
        if status != 200:
            logger.error(f"Failed to fetch products for keyword: {keyword}")
            return

        items = data.get("data", {}).get("items") or data.get("items") or []
        for item in items:
            await self._create_candidate(item, strategy="KEYWORD_SEARCH")

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
    ):
        async with self._ai_semaphore:
            return await self._execute_create_candidate(
                item, strategy, benchmark_id, seasonal_score, margin_score, spec_data, thumbnail_url, visual_analysis, expert_match_score, expert_match_reason
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
        ai = AIService()
        
        # Find raw record
        raw_entry = self.db.execute(
            select(SupplierItemRaw)
            .where(SupplierItemRaw.supplier_code == candidate.supplier_code)
            .where(SupplierItemRaw.item_code == candidate.supplier_item_id)
        ).scalar_one_or_none()
        
        if not raw_entry:
            logger.error(f"Cannot approve candidate: SupplierItemRaw not found for {candidate.supplier_item_id}")
            return

        # Clean original name
        cleaned_name = clean_product_name(candidate.name)
        
        # Optimize SEO
        seo = await ai.optimize_seo(cleaned_name, candidate.seo_keywords or [], context=candidate.visual_analysis)
        processed_name = seo.get("title") or cleaned_name
        processed_keywords = seo.get("tags") or candidate.seo_keywords
        
        product = Product(
            supplier_item_id=raw_entry.id, # Link to raw record
            name=cleaned_name,
            processed_name=processed_name,
            processed_keywords=processed_keywords,
            cost_price=candidate.supply_price,
            selling_price=int(candidate.supply_price * 1.3), # Default 30% margin
            status="DRAFT",
            processing_status="PENDING",
            processed_image_urls=[candidate.thumbnail_url] if candidate.thumbnail_url else []
        )
        self.db.add(product)
        self.db.flush() # ID 확보
        
        # 1.1 Parse and save options
        raw_data = raw_entry.raw if isinstance(raw_entry.raw, dict) else {}
        options_data = raw_data.get("options") or []
        
        if options_data:
            for opt in options_data:
                # 오너클랜 옵션 구조: {'optionAttributes': [{'name': '색상', 'value': '블랙'}], 'price': 10000, 'quantity': 50, 'key': '...'}
                attrs = opt.get("optionAttributes") or []
                opt_name = "/".join([a.get("name", "") for a in attrs if a.get("name")]) or "기본"
                opt_value = "/".join([a.get("value", "") for a in attrs if a.get("value")]) or "-"
                
                # 가산가 적용 확인 (price가 옵션 단독가인지, 차액인지 확인 필요. 오너클랜은 보통 개별 단가)
                opt_price = self._to_int(opt.get("price")) or product.cost_price
                
                new_opt = ProductOption(
                    product_id=product.id,
                    option_name=opt_name,
                    option_value=opt_value,
                    cost_price=opt_price,
                    selling_price=int(opt_price * 1.3), # 동일 마진 적용
                    stock_quantity=self._to_int(opt.get("quantity")) or 0,
                    external_option_key=opt.get("key")
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
            
            # Basic validation
            if not name or price <= 0:
                continue
                
            candidate = SourcingCandidate(
                supplier_code="ownerclan",
                supplier_item_id=str(raw.item_code),
                name=str(name),
                supply_price=int(price),
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
