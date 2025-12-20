import logging
import uuid
from typing import List

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.embedding_service import EmbeddingService
from app.models import BenchmarkProduct, SupplierAccount, SupplierItemRaw, SourcingCandidate
from app.ownerclan_client import OwnerClanClient
from app.settings import settings
from app.services.ai.agents.sourcing_agent import SourcingAgent

logger = logging.getLogger(__name__)


class SourcingService:
    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = EmbeddingService()
        self.sourcing_agent = SourcingAgent(db)

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
        except Exception:  # noqa: BLE001
            return None

    async def execute_keyword_sourcing(self, keywords: List[str], min_margin: float = 0.15):
        """
        Strategy 1: Simple Keyword Sourcing
        Searches OwnerClan for keywords, filters by margin, and creates candidates.
        """
        logger.info("Starting Keyword Sourcing for: %s", keywords)

        client = self._get_ownerclan_primary_client(user_type="seller")

        found_items: list[dict] = []
        for kw in keywords:
            status_code, data = client.get_products(keyword=kw, limit=50)
            if status_code != 200:
                logger.warning("오너클랜 상품 검색 실패: HTTP %s (keyword=%s)", status_code, kw)
                continue
            found_items.extend(self._extract_items(data))

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
                thumbnail_url = (
                    item.get("thumbnail_url")
                    or item.get("thumbnailUrl")
                    or (item.get("images")[0] if isinstance(item.get("images"), list) and item.get("images") else None)
                )
                await self._create_candidate(
                    item,
                    strategy="KEYWORD",
                    margin_score=margin,
                    thumbnail_url=thumbnail_url,
                )

    async def execute_benchmark_sourcing(self, benchmark_id: uuid.UUID):
        """
        Strategy 2: Benchmark Sourcing that leverages the LangGraph-based sourcing agent.
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
        }

        try:
            result_state = await self.sourcing_agent.run(str(benchmark_id), input_data)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Benchmark sourcing agent failed: %s", exc)
            return

        candidate_results = (result_state or {}).get("candidate_results") or []
        specs = (result_state or {}).get("specs")
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
            )

    async def _create_candidate(
        self,
        item: dict,
        strategy: str,
        benchmark_id: uuid.UUID | None = None,
        seasonal_score: float | None = None,
        margin_score: float | None = None,
        spec_data: dict | None = None,
        thumbnail_url: str | None = None,
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
            return

        name = item.get("item_name") or item.get("name") or item.get("itemName") or "Unknown"
        supply_price = self._to_int(
            item.get("supply_price")
            or item.get("supplyPrice")
            or item.get("fixedPrice")
            or item.get("price")
        ) or 0

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
                if not candidate_images and isinstance(item.get("images"), list):
                    candidate_images = item.get("images")[:1]

                embedding = await self.embedding_service.generate_rich_embedding(
                    candidate_text,
                    image_urls=candidate_images,
                )

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
            status="PENDING",
        )

        self.db.add(candidate)
        self.db.commit()
        similarity_text = f"{similarity_score:.4f}" if similarity_score is not None else "n/a"
        logger.info("Created candidate: %s (Similarity=%s)", candidate.name, similarity_text)

    def find_similar_items_in_raw(self, embedding: List[float], limit: int = 10) -> List[SupplierItemRaw]:
        """
        Finds similar items in SourcingCandidate using vector similarity.
        """
        stmt = (
            select(SourcingCandidate)
            .order_by(SourcingCandidate.embedding.cosine_distance(embedding))
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

    def import_from_raw(self, limit: int = 1000) -> int:
        """
        Converts available SupplierItemRaw data into SourcingCandidate entries.
        """
        logger.info("Starting bulk import from SupplierItemRaw...")

        stmt = (
            select(SupplierItemRaw)
            .where(SupplierItemRaw.supplier_code == "ownerclan")
            .order_by(desc(SupplierItemRaw.fetched_at))
            .limit(limit * 5)
        )

        raw_items = self.db.scalars(stmt).all()
        count = 0

        for raw in raw_items:
            try:
                if not raw.item_code:
                    continue

                data = raw.raw if isinstance(raw.raw, dict) else {}
                name = data.get("item_name") or data.get("name") or data.get("itemName") or "Unknown"
                supply_price = (
                    self._to_int(
                        data.get("supply_price")
                        or data.get("supplyPrice")
                        or data.get("fixedPrice")
                        or data.get("price")
                    )
                    or 0
                )

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

            except Exception as exc:  # noqa: BLE001
                logger.error("Error converting raw item %s: %s", raw.id, exc)

        self.db.commit()
        logger.info("Imported %s candidates from raw data.", count)
        return count
