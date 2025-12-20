import logging
from typing import List, Optional
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, desc

from app.models import Product, SourcingCandidate, BenchmarkProduct, SupplierItemRaw, SupplierAccount
from app.ownerclan_client import OwnerClanClient
from app.settings import settings
from app.services.ai import AIService
from app.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

class SourcingService:
    def __init__(self, db: Session):
        self.db = db
        self.clant = OwnerClanClient(
            auth_url=settings.ownerclan_auth_url,
            api_base_url=settings.ownerclan_api_base_url,
            graphql_url=settings.ownerclan_graphql_url
        )
        self.embedding_service = EmbeddingService()
        self.ai_service = AIService()

    def _get_ownerclan_primary_client(self, user_type: str = "seller") -> OwnerClanClient:
        account = (
            self.db.query(SupplierAccount)
            .filter(SupplierAccount.supplier_code == "ownerclan")
            .filter(SupplierAccount.user_type == user_type)
            .filter(SupplierAccount.is_primary.is_(True))
            .filter(SupplierAccount.is_active.is_(True))
            .one_or_none()
        )
        if not account:
            raise RuntimeError("오너클랜 대표 계정이 설정되어 있지 않습니다")

        return OwnerClanClient(
            auth_url=settings.ownerclan_auth_url,
            api_base_url=settings.ownerclan_api_base_url,
            graphql_url=settings.ownerclan_graphql_url,
            access_token=account.access_token,
        )

    def _extract_items(self, data: dict) -> list[dict]:
        if not isinstance(data, dict):
            return []
        data_obj = data.get("data")
        if not isinstance(data_obj, dict):
            return []
        items_obj = data_obj.get("items")
        if items_obj is None and isinstance(data_obj.get("data"), dict):
            items_obj = data_obj.get("data").get("items")
        if isinstance(items_obj, list):
            return [it for it in items_obj if isinstance(it, dict)]
        return []

    def _to_int(self, value) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except Exception:
            return None

    async def execute_keyword_sourcing(self, keywords: List[str], min_margin: float = 0.15):
        """
        Strategy 1: Simple Keyword Sourcing
        Searches OwnerClan for keywords, filters by margin, and creates candidates.
        """
        logger.info(f"Starting Keyword Sourcing for: {keywords}")

        client = self._get_ownerclan_primary_client(user_type="seller")
        
        # 1. Search OwnerClan
        found_items = []
        for kw in keywords:
            status_code, data = client.get_products(keyword=kw, limit=50)
            if status_code != 200:
                logger.warning(f"오너클랜 상품 검색 실패: HTTP {status_code} (keyword={kw})")
                continue
            found_items.extend(self._extract_items(data))
        
        # 2. Process Items
        for item in found_items:
            supply_price = self._to_int(
                item.get("supply_price")
                or item.get("supplyPrice")
                or item.get("fixedPrice")
                or item.get("price")
            )
            selling_price = self._to_int(
                item.get("selling_price")
                or item.get("sellingPrice")
                or item.get("fixedPrice")
                or item.get("price")
            )

            margin: float | None = None
            if selling_price and selling_price > 0 and supply_price is not None:
                margin = (selling_price - supply_price) / selling_price

            if margin is None or margin >= min_margin:
<<<<<<< Updated upstream
                self._create_candidate(item, strategy="KEYWORD", margin_score=margin)
=======
                await self._create_candidate(
                    item, 
                    strategy="KEYWORD", 
                    margin_score=margin,
                    thumbnail_url=item.get("thumbnail_url") or (item.get("images")[0] if item.get("images") else None)
                )
>>>>>>> Stashed changes

    def execute_benchmark_sourcing(self, benchmark_id: uuid.UUID):
        """
        Strategy 2: Benchmark Sourcing (Gap Analysis & Spec Match)
        """
        benchmark = self.db.execute(select(BenchmarkProduct).where(BenchmarkProduct.id == benchmark_id)).scalar_one_or_none()
        if not benchmark:
            logger.error(f"Benchmark product {benchmark_id} not found")
            return

<<<<<<< Updated upstream
        client = self._get_ownerclan_primary_client(user_type="seller")

        # 1. Analyze Benchmark (if not already)
        if not benchmark.pain_points:
            # Use Tier 1 (Gemini) for complex reasoning like Pain Point Analysis
            benchmark.pain_points = self.ai_service.analyze_pain_points(benchmark.detail_html or benchmark.name, provider="gemini")
            self.db.commit()
            
        search_terms = [benchmark.name] 
        # 3. Search OwnerClan
        found_items = []
        status_code, data = client.get_products(keyword=benchmark.name, limit=50)
        if status_code == 200:
            found_items = self._extract_items(data)
        else:
            logger.warning(f"오너클랜 상품 검색 실패: HTTP {status_code} (keyword={benchmark.name})")

        # 4. Score and Filter
        for item in found_items:
            candidate_item = item 
            
            # A. Spec Matching
            # Use 'auto' (Tier 2/Ollama typically sufficient for extraction)
            specs = self.ai_service.extract_specs(str(candidate_item), provider="auto")
            
            # B. Gap Analysis skipped for brevity in this step
            
            # C. Seasonality & Event Scoring
            season_data = self.ai_service.predict_seasonality(
                (candidate_item.get("item_name") or candidate_item.get("name") or ""),
                provider="auto"
            )
            current_month_score = season_data.get("current_month_score", 0.0)
            
            # D. Create Candidate
            self._create_candidate(
                candidate_item, 
                strategy="BENCHMARK", 
                benchmark_id=benchmark.id,
                seasonal_score=current_month_score,
                spec_data=specs
=======
        # LangGraph 에이전트 실행
        input_data = {
            "name": benchmark.name,
            "detail_html": benchmark.detail_html,
            "price": benchmark.price
        }
        
        result = await self.sourcing_agent.run(str(benchmark_id), input_data)
        
        # 에이전트 결과를 바탕으로 기존 _create_candidate 호출 로직 유지가능
        for candidate_data in result.get("candidate_results", []):
            await self._create_candidate(
                candidate_data,
                strategy="BENCHMARK_AGENT",
                benchmark_id=benchmark.id,
                seasonal_score=candidate_data.get("seasonal_score"),
                spec_data=result.get("specs"),
                thumbnail_url=candidate_data.get("thumbnail_url")
>>>>>>> Stashed changes
            )

    async def _create_candidate(
        self,
        item: dict,
        strategy: str,
        benchmark_id: uuid.UUID = None,
        seasonal_score: float | None = None,
        margin_score: float | None = None,
        spec_data: dict | None = None,
    ):
        
        # Check if already exists
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
            ).scalars().first()
        )
        if exists:
            return

        name = item.get("item_name") or item.get("name") or item.get("itemName") or "Unknown"
        supply_price = self._to_int(
            item.get("supply_price")
            or item.get("supplyPrice")
            or item.get("fixedPrice")
            or item.get("price")
        )
        if supply_price is None:
            supply_price = 0

        # Generate Rich Embedding and Similarity Score
        embedding = None
        similarity_score = None
        
        if benchmark_id:
            benchmark = self.db.execute(select(BenchmarkProduct).where(BenchmarkProduct.id == benchmark_id)).scalar_one_or_none()
            if benchmark and benchmark.embedding is not None:
                # 후보 상품의 풍부한 임베딩 생성 (이름 + 썸네일 기반)
                # 상세 페이지 데이터가 있다면 더 정확하겠지만, 현재 검색 결과에는 썸네일 정도가 최선일 수 있음
                candidate_text = f"{name} {item.get('detail_html', '')}".strip()
                candidate_images = [thumbnail_url] if thumbnail_url else []
                if not candidate_images and item.get("images"):
                    candidate_images = item.get("images")[:1]
                
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
            status="PENDING"
        )
        
<<<<<<< Updated upstream
        # Optimize SEO immediately? Or lazy load. Let's do lazy for performance.
        self.db.add(candidate)
        self.db.commit()
        logger.info(f"Created candidate: {candidate.name}")
=======
        self.db.add(candidate)
        self.db.commit()
        logger.info(f"Created candidate: {candidate.name} (Similarity={similarity_score:.4f} if relevant)")

    def find_similar_items_in_raw(self, embedding: List[float], limit: int = 10) -> List[SupplierItemRaw]:
        """
        Finds similar items in SupplierItemRaw table using vector similarity.
        Note: This requires SupplierItemRaw to have an embedding column and pgvector support.
        """
        # 현재 SupplierItemRaw에는 embedding 필드가 없으므로, 향후 확장을 위해 인터페이스만 정의하거나
        # 필요시 모델 업데이트가 선행되어야 합니다.
        # 일단 SourcingCandidate에서 검색하는 로직을 우선 구현합니다.
        stmt = (
            select(SourcingCandidate)
            .order_by(SourcingCandidate.embedding.cosine_distance(embedding))
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

    def import_from_raw(self, limit: int = 1000) -> int:
        """
        Converts available SupplierItemRaw data into SourcingCandidate.
        Useful for bulk collection where data lands in raw table first.
        """
        logger.info("Starting bulk import from SupplierItemRaw...")

        # 1. Fetch raw items from Source DB
        # We fetch decent amount of latest items and filter in memory
        stmt = (
            select(SupplierItemRaw)
            .where(SupplierItemRaw.supplier_code == "ownerclan")
            .order_by(desc(SupplierItemRaw.fetched_at))
            .limit(limit * 5)  # Fetch more to find new ones
        )
        
        raw_items = self.db.scalars(stmt).all()
        count = 0
        
        for raw in raw_items:
            try:
                if not raw.item_code:
                    continue

                data = raw.raw if isinstance(raw.raw, dict) else {}
                name = data.get("item_name") or data.get("name") or data.get("itemName") or "Unknown"
                
                supply_price = self._to_int(
                    data.get("supply_price")
                    or data.get("supplyPrice")
                    or data.get("fixedPrice")
                    or data.get("price")
                ) or 0

                insert_stmt = (
                    insert(SourcingCandidate)
                    .values(
                        supplier_code="ownerclan",
                        supplier_item_id=str(raw.item_code),
                        name=str(name),
                        supply_price=int(supply_price),
                        thumbnail_url=data.get("thumbnail_url") or (data.get("images")[0] if data.get("images") else None),
                        source_strategy="BULK_COLLECT",
                        status="PENDING",
                    )
                    .on_conflict_do_nothing()
                )

                result = self.db.execute(insert_stmt)
                if result.rowcount:
                    count += int(result.rowcount)

                if count >= limit:
                    break

            except Exception as e:
                logger.error(f"Error converting raw item {raw.id}: {e}")
                
        self.db.commit()
        logger.info(f"Imported {count} candidates from raw data.")
        return count
>>>>>>> Stashed changes
