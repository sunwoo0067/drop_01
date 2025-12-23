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
            if benchmark and benchmark.embedding is not None:
                candidate_text = f"{name} {item.get('detail_html', '')}".strip()
                candidate_images = [final_thumbnail_url] if final_thumbnail_url else []
                embedding = await self.embedding_service.generate_rich_embedding(candidate_text, image_urls=candidate_images)
                if embedding:
                    similarity_score = self.embedding_service.compute_similarity(benchmark.embedding, embedding)

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
            final_score=expert_match_score, # Mapping expert match score to final_score
            status="PENDING",
        )

        self.db.add(candidate)
        self.db.commit()
        logger.info("Created candidate: %s (Expert Score=%s)", candidate.name, expert_match_score)

    def find_similar_items_in_raw(self, embedding: List[float], limit: int = 10) -> List[SourcingCandidate]:
        stmt = (
            select(SourcingCandidate)
            .order_by(SourcingCandidate.embedding.cosine_distance(embedding))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def import_from_raw(self, limit: int = 1000) -> int:
        pass
