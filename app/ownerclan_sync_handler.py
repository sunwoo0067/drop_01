"""
OwnerClan 아이템 동기화 핸들러.

기존 큰 함수들을 단계별 핸들러로 분해하여 유지보수/테스트 용이성을 확보합니다.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple, Any, List
from datetime import datetime, timedelta, timezone
import time
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import SupplierItemRaw, SupplierSyncJob
from app.ownerclan_client import OwnerClanClient
from app.settings import settings
from app.services.detail_html_normalizer import normalize_ownerclan_html
from app.services.ownerclan_utils import (
    OwnerClanJobResult,
    _parse_ownerclan_datetime,
    _sanitize_json,
    get_sync_state,
    upsert_sync_state,
)


logger = logging.getLogger(__name__)







@dataclass
class OwnerClanItemSyncHandler:
    """
    오너클랜 아이템 동기화 핸들러.
    
    1단계: 상품 키 목록 수집 (최대 5,000개)
    2단계: 수집된 키들에 대한 상세 정보 일괄 조회
    3단계: 아이템 정규화 및 DB 저장 (idempotent upsert)
    4단계: 메인 동기화 메소드 (orchestration)
    """
    
    session: Session
    job: SupplierSyncJob
    client: OwnerClanClient
    
    # 배치 설정
    batch_size: int = 100
    max_pages: int = 50
    max_items_per_batch: int = 5000
    batch_commit_size: int = field(default_factory=lambda: settings.ownerclan_batch_commit_size) 
    
    # 성능 측정용 (PR-4)
    start_time: float = field(default_factory=time.time)
    commit_count: int = 0
    
    # 상태 관리 (재개 가능성)
    state: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """초기화: job.state 로드"""
        if isinstance(self.job.params, dict):
            self.state = self.job.params.get("sync_state", {})
    
    def save_state(self):
        """상태를 job.params에 저장"""
        if not isinstance(self.job.params, dict):
            self.job.params = {}
        self.job.params["sync_state"] = self.state
        # progress는 state["total_processed"]를 활용
        self.job.progress = self.state.get("total_processed", 0)
    
    def _log_api_call(
        self,
        endpoint_name: str,
        status_code: Optional[int],
        error_message: Optional[str] = None,
        key_count: int = 0
    ):
        """API 호출 요약 로깅"""
        logger.debug(
            f"[{endpoint_name}] HTTP {status_code if status_code else 'ERROR'} | "
            f"keys={key_count} | error={error_message}"
        )
    
    @retry(
        stop=stop_after_attempt(settings.ownerclan_retry_count),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((TimeoutError, ConnectionError, RuntimeError)),
        reraise=True,
        # 429나 5xx 에러는 RuntimeError로 래핑되어 올라올 수 있음
        before_sleep=lambda retry_state: logger.warning(
            f"API 재시도 중... ({retry_state.attempt_number}회째): {retry_state.outcome.exception()}"
        )
    )
    def fetch_item_keys_batch(
        self,
        date_from_ms: int,
        date_to_ms: int,
        cursor: Optional[str],
        first: int = 100
    ) -> Tuple[List[str], Optional[str], int]:
        """
        1단계: 상품 키 목록 수집 (최대 5,000개 수집 시도)
        """
        keys_batch = []
        page_count = 0
        current_cursor = cursor
        
        for _ in range(50):
            page_count += 1
            
            # GraphQL 쿼리
            after_fragment = "null" if not current_cursor else f'"{current_cursor}"'
            
            list_query = f"""
            query {{
              allItems(dateFrom: {date_from_ms}, dateTo: {date_to_ms}, after: {after_fragment}, first: {first}) {{
                pageInfo {{
                  hasNextPage
                  endCursor
                }}
                edges {{
                  node {{
                    key
                    updatedAt
                  }}
                }}
              }}
            }}
            """
            
            try:
                status_code, payload = self.client.graphql(list_query)
            except Exception as e:
                logger.error(f"오너클랜 목록 수집 중 네트워크 오류: {e}")
                raise # tenacity가 재시도할 수 있도록 raise

            if status_code == 401:
                raise RuntimeError("오너클랜 인증이 만료되었습니다(401). 토큰을 갱신해 주세요")
            if status_code >= 400:
                raise RuntimeError(f"오너클랜 GraphQL 호출 실패: HTTP {status_code}")
            if payload.get("errors"):
                raise RuntimeError(f"오너클랜 GraphQL 오류: {payload.get('errors')}")
            
            data = payload.get("data") or {}
            edges = ((data.get("allItems") or {}).get("edges") or [])
            for edge in edges:
                node = (edge or {}).get("node") or {}
                key = node.get("key")
                if key:
                    keys_batch.append(key)
            
            page_info = (data.get("allItems") or {}).get("pageInfo") or {}
            current_cursor = page_info.get("endCursor")
            has_next = page_info.get("hasNextPage")
            
            self._log_api_call("allItems_list", status_code, key_count=len(edges))
            
            if not has_next or not current_cursor:
                break
            
            # API 제한 준수
            time.sleep(settings.ownerclan_api_sleep)
        
        return keys_batch, current_cursor, page_count
    
    @retry(
        stop=stop_after_attempt(settings.ownerclan_retry_count),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((TimeoutError, ConnectionError, RuntimeError)),
        reraise=True,
        before_sleep=lambda retry_state: logger.warning(
            f"상세 정보 조회 재시도 중... ({retry_state.attempt_number}회째): {retry_state.outcome.exception()}"
        )
    )
    def fetch_item_details_batch(self, keys_batch: List[str]) -> List[dict]:
        """
        2단계: 수집된 키들에 대한 상세 정보 일괄 조회
        """
        # ... (상세 쿼리는 생략 가능하지만 구조상 전체 교체)
        detail_query = """
        query ($keys: [ID!]!) {
          itemsByKeys(keys: $keys) {
            createdAt
            updatedAt
            key
            name
            model
            production
            origin
            id
            price
            pricePolicy
            fixedPrice
            searchKeywords
            category {
              key
              name
              fullName
              parent { key }
            }
            content
            shippingFee
            shippingType
            options {
              optionAttributes {
                name
                value
              }
              price
              quantity
              key
            }
            taxFree
            adultOnly
            returnable
            noReturnReason
            guaranteedShippingPeriod
            openmarketSellable
            boxQuantity
            attributes
            closingTime
            metadata
            images(size: large)
            status
          }
        }
        """
        
        try:
            status_code, detail_payload = self.client.graphql(
                detail_query,
                variables={"keys": keys_batch}
            )
        except Exception as e:
            logger.error(f"상세 정보 조회 중 네트워크 오류: {e}")
            raise

        if status_code != 200:
            raise RuntimeError(f"상세 조회 실패: HTTP {status_code}")
        
        items = ((detail_payload.get("data") or {}).get("itemsByKeys") or [])
        
        # HTML 정규화
        for item in items:
            content = item.get("content") or ""
            if isinstance(content, str) and content.strip():
                item["detail_html"] = normalize_ownerclan_html(content)
        
        self._log_api_call("itemsByKeys_bulk", status_code, key_count=len(items))
        return items
    
    def normalize_and_save_items(self, items: List[dict]) -> int:
        """
        3단계: 아이템 정규화 및 DB 저장 (idempotent upsert + 배치 커밋)
        """
        processed_count = 0
        total_in_batch = len(items)
        
        try:
            for item in items:
                item_code = item.get("key") or item.get("id")
                if not item_code:
                    continue
                
                source_updated_at = _parse_ownerclan_datetime(item.get("updatedAt"))
                
                stmt = insert(SupplierItemRaw).values(
                    supplier_code="ownerclan",
                    item_code=str(item_code),
                    item_key=str(item.get("key")),
                    item_id=str(item.get("id")),
                    name=item.get("name") or "",
                    source_updated_at=source_updated_at,
                    raw=_sanitize_json(item),
                    fetched_at=datetime.now(timezone.utc),
                )
                
                stmt = stmt.on_conflict_do_update(
                    index_elements=["supplier_code", "item_code"],
                    set_={
                        "item_key": stmt.excluded.item_key,
                        "item_id": stmt.excluded.item_id,
                        "raw": stmt.excluded.raw,
                        "fetched_at": stmt.excluded.fetched_at,
                    },
                )
                self.session.execute(stmt)
                processed_count += 1
                
                # 배치 커밋 로직
                if processed_count % self.batch_commit_size == 0:
                    # 1. 상태 업데이트 (동일 트랜잭션에 포함)
                    self.state["total_processed"] = self.state.get("total_processed", 0) + self.batch_commit_size
                    self.save_state()
                    
                    # 2. DB 일괄 커밋 (아이템 + 작업 상태)
                    self.session.commit()
                    self.commit_count += 1
                    
                    elapsed = time.time() - self.start_time
                    logger.info(
                        f"배치 커밋 성공: 누적 {self.state['total_processed']}개 | "
                        f"속도: {(self.state['total_processed'] / (elapsed if elapsed > 0 else 0.1)):.2f} items/sec"
                    )
            
            # 최종 잔여분 커밋
            remaining = processed_count % self.batch_commit_size
            if remaining != 0:
                self.state["total_processed"] = self.state.get("total_processed", 0) + remaining
                self.save_state()
                self.session.commit()
                logger.debug(f"최종 잔여 배치 커밋: {remaining}개")
                
        except Exception as e:
            logger.error(f"아이템 저장 중 오류 발생 (롤백): {e}")
            self.session.rollback()
            raise
        
        return processed_count
    
    def sync(self) -> OwnerClanJobResult:
        """
        4단계: 메인 동기화 메소드 (orchestration)
        """
        params = dict(self.job.params or {})
        date_from_ms = int(params.get("dateFrom", 0))
        date_to_ms = int(params.get("dateTo", int(time.time() * 1000)))
        current_cursor = params.get("after")
        first = int(params.get("first", 100))
        
        # 재개 로직
        if self.state.get("last_cursor") and not current_cursor:
            current_cursor = self.state["last_cursor"]
            logger.info(f"재개 시작: cursor={current_cursor}, total={self.state.get('total_processed', 0)}")
        
        page_count = 0
        self.start_time = time.time()
        
        while True:
            # 1. 키 수집
            keys_batch, next_cursor, pages_in_loop = self.fetch_item_keys_batch(
                date_from_ms=date_from_ms,
                date_to_ms=date_to_ms,
                cursor=current_cursor,
                first=first
            )
            page_count += pages_in_loop
            
            if not keys_batch:
                logger.info("더 이상 수집할 아이템 키가 없습니다.")
                break
            
            # 2. 상세 조회
            items = self.fetch_item_details_batch(keys_batch)
            
            # 3. 저장 및 커밋
            processed_in_batch = self.normalize_and_save_items(items)
            
            # 4. 상태 갱신
            current_cursor = next_cursor
            self.state["last_cursor"] = current_cursor
            
            # 종료 조건 확인
            max_items = int(params.get("maxItems", 0))
            current_total = self.state.get("total_processed", 0)
            if max_items > 0 and current_total >= max_items:
                logger.info(f"최대 처리 개수 도달 ({current_total}/{max_items})")
                break
            
            if self.max_pages > 0 and page_count >= self.max_pages:
                logger.info(f"최대 페이지 도달 ({page_count}/{self.max_pages})")
                break
            
            if not current_cursor:
                break
            
            # API 제한 준수
            time.sleep(settings.ownerclan_api_sleep_loop)
        
        # 동기화 완료 통계
        elapsed = time.time() - self.start_time
        self.state["sync_completed_at"] = datetime.now(timezone.utc).isoformat()
        self.state["elapsed_seconds"] = round(elapsed, 2)
        self.save_state()
        self.session.commit()
        
        return OwnerClanJobResult(processed=self.state.get("total_processed", 0))
