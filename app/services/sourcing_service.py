import logging
import uuid
import asyncio
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SourcingCandidate, BenchmarkProduct
from app.services.ai.agents.sourcing_agent import SourcingAgent
from app.embedding_service import EmbeddingService
from app.settings import settings

logger = logging.getLogger(__name__)

class SourcingService:
    def __init__(self, db: Session):
        self.db = db
        self.sourcing_agent = SourcingAgent(db)
        self.embedding_service = EmbeddingService()
        self._ai_semaphore = asyncio.Semaphore(1)

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

    async def execute_keyword_sourcing(self, keyword: str, limit: int = 30):
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
        expanded = ai.expand_keywords(keyword)
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
        from app.models import SupplierItemRaw
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
        profit_score = 0.0
        if supply_price > 0 and (benchmark_price := (benchmark.price if benchmark else 0)) > 0:
            margin_rate = (benchmark_price - supply_price) / benchmark_price
            if margin_rate >= 0.2: profit_score = 1.0
            elif margin_rate > 0: profit_score = margin_rate / 0.2
        
        # Seasonality (30%)
        # already provided as seasonal_score arg, or default to 0.5
        s_score = seasonal_score if seasonal_score is not None else 0.5
        
        # Competition (20%) - Placeholder (Default high if unknown)
        comp_score = 1.0 
        
        # Quality (10%) - Heuristic based on rating or description quality
        quality_score = min(1.0, len(item.get("detail_html", "")) / 5000.0)

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
        if not candidate or candidate.status == "APPROVED":
            return

        candidate.status = "APPROVED"
        self.db.commit()

        # 1. Create Product
        from app.models import Product, SupplierItemRaw
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

        # Optimize SEO
        seo = ai.optimize_seo(candidate.name, candidate.seo_keywords or [], context=candidate.visual_analysis)
        processed_name = seo.get("title") or candidate.name
        processed_keywords = seo.get("tags") or candidate.seo_keywords
        
        product = Product(
            supplier_item_id=raw_entry.id, # Link to raw record
            name=candidate.name,
            processed_name=processed_name,
            processed_keywords=processed_keywords,
            cost_price=candidate.supply_price,
            selling_price=int(candidate.supply_price * 1.3), # Default 30% margin
            status="DRAFT",
            processing_status="PENDING",
            processed_image_urls=[candidate.thumbnail_url] if candidate.thumbnail_url else []
        )
        self.db.add(product)
        self.db.commit()
        
        logger.info(f"Promoted candidate to Product: {product.name} (ID: {product.id})")
        
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

    def import_from_raw(self, limit: int = 1000) -> int:
        pass
