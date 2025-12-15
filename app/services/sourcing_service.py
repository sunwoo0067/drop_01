import logging
from typing import List, Optional
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, desc

from app.models import Product, SourcingCandidate, BenchmarkProduct, SupplierItemRaw
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

    def _get_api_token(self):
        # TODO: Implement proper token management/caching
        # For now, assumes we have user credentials in settings or handled elsewhere
        # Ideally this should be injected or managed by a TokenManager
        return "temp_token" # Placeholder: Integration with TokenManager needed

    async def execute_keyword_sourcing(self, keywords: List[str], min_margin: float = 0.15):
        """
        Strategy 1: Simple Keyword Sourcing
        Searches OwnerClan for keywords, filters by margin, and creates candidates.
        """
        logger.info(f"Starting Keyword Sourcing for: {keywords}")
        
        # 1. Search OwnerClan
        found_items = []
        for kw in keywords:
            status, data = self.clant.get_products(keyword=kw, limit=50) 
            if status == 200 and "data" in data:
                 found_items.extend(data["data"]["items"])
        
        # 2. Process Items
        for item in found_items:
            supply_price = item.get("supply_price", 99999999)
            selling_price = item.get("selling_price", 0) 
            
            if selling_price > 0:
                margin = (selling_price - supply_price) / selling_price
                if margin >= min_margin:
                    self._create_candidate(item, strategy="KEYWORD", margin_score=margin)

    async def execute_benchmark_sourcing(self, benchmark_id: uuid.UUID):
        """
        Strategy 2: Benchmark Sourcing (Gap Analysis & Spec Match)
        """
        benchmark = self.db.execute(select(BenchmarkProduct).where(BenchmarkProduct.id == benchmark_id)).scalar_one_or_none()
        if not benchmark:
            logger.error(f"Benchmark product {benchmark_id} not found")
            return

        # 1. Analyze Benchmark (if not already)
        if not benchmark.pain_points:
            # Use Tier 1 (Gemini) for complex reasoning like Pain Point Analysis
            benchmark.pain_points = self.ai_service.analyze_pain_points(benchmark.detail_html or benchmark.name, provider="gemini")
            self.db.commit()
            
        search_terms = [benchmark.name] 
        
        # 3. Search OwnerClan
        found_items = []
        status, data = self.clant.get_products(keyword=benchmark.name, limit=50)
        if status == 200 and "data" in data and "items" in data["data"]:
             found_items = data["data"]["items"]

        # 4. Score and Filter
        for item in found_items:
            candidate_item = item 
            
            # A. Spec Matching
            # Use 'auto' (Tier 2/Ollama typically sufficient for extraction)
            specs = self.ai_service.extract_specs(str(candidate_item), provider="auto")
            
            # B. Gap Analysis skipped for brevity in this step
            
            # C. Seasonality & Event Scoring
            season_data = self.ai_service.predict_seasonality(candidate_item.get("name", ""), provider="auto")
            current_month_score = season_data.get("current_month_score", 0.0)
            
            # D. Create Candidate
            self._create_candidate(
                candidate_item, 
                strategy="BENCHMARK", 
                benchmark_id=benchmark.id,
                seasonal_score=current_month_score,
                spec_data=specs
            )

    def _create_candidate(self, item: dict, strategy: str, benchmark_id: uuid.UUID = None, 
                          seasonal_score: float = 0.0, margin_score: float = 0.0, spec_data: dict = None):
        
        # Check if already exists
        supplier_id = item.get("item_code") # Adjust key based on OwnerClan API
        exists = self.db.execute(select(SourcingCandidate).where(SourcingCandidate.supplier_item_id == str(supplier_id))).first()
        if exists:
            return

        candidate = SourcingCandidate(
            supplier_code="OWNERCLAN",
            supplier_item_id=str(supplier_id),
            name=item.get("name", "Unknown"),
            supply_price=int(item.get("supply_price", 0)),
            source_strategy=strategy,
            benchmark_product_id=benchmark_id,
            seasonal_score=seasonal_score,
            margin_score=margin_score,
            spec_data=spec_data,
            status="PENDING"
        )
        
        # Optimize SEO immediately? Or lazy load. Let's do lazy for performance.
        
        self.db.add(candidate)
        self.db.commit()
        logger.info(f"Created candidate: {candidate.name}")
