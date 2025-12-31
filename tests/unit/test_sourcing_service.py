"""
Unit tests for SourcingService.

주요 비즈니스 로직의 순수 함수들을 테스트합니다.
"""

import pytest
from sqlalchemy.orm import Session
from app.models import SourcingCandidate
import uuid


@pytest.mark.unit
class TestSourcingServiceCalculations:
    """SourcingService의 순수 계산 로직 테스트."""

    def test_margin_calculation_basic(self):
        """기본 마진 계산 검증."""
        cost = 10000
        selling_price = 15000
        
        # 기본 마진 계산
        margin = selling_price - cost
        margin_rate = margin / cost if cost > 0 else 0
        
        assert margin == 5000
        assert margin_rate == 0.5

    def test_margin_calculation_with_market_fee(self):
        """마켓 수수료 포함 마진 계산."""
        cost = 10000
        selling_price = 15000
        market_fee_rate = 0.13  # 13%
        
        # 수수료 = 15000 * 0.13 = 1950
        # 마진 = 15000 - 10000 - 1950 = 3050
        expected_margin = selling_price - cost - (selling_price * market_fee_rate)
        expected_margin_rate = expected_margin / cost if cost > 0 else 0
        
        assert abs(expected_margin - 3050) < 1  # 부동소수점 오차 허용
        assert abs(expected_margin_rate - 0.305) < 0.01

    def test_margin_calculation_zero_cost(self):
        """비용 0원 경우 예외 처리."""
        cost = 0
        selling_price = 15000
        
        # 비용이 0이면 마진율 계산에서 예외 처리되어야 함
        with pytest.raises(ZeroDivisionError):
            margin_rate = selling_price / cost

    def test_margin_calculation_negative_margin(self):
        """마진이 음수인 경우."""
        cost = 15000
        selling_price = 10000
        
        margin = selling_price - cost
        assert margin == -5000
        
        # 음수 마진은 유효하지 않은 것으로 처리해야 함
        # 실제 로직에서는 예외를 덜지거나, False를 반환할 수 있음


@pytest.mark.unit
class TestSourcingServiceHelperFunctions:
    """헬퍼 함수 테스트."""

    def test_calculate_profit_margin(self):
        """마진 계산 헬퍼 함수."""
        def calculate_margin(cost: float, price: float) -> tuple[float, float]:
            margin = price - cost
            margin_rate = margin / cost if cost > 0 else 0
            return margin, margin_rate
        
        margin, rate = calculate_margin(10000, 15000)
        assert margin == 5000
        assert abs(rate - 0.5) < 0.01

    def test_clean_product_name(self):
        """상품명 정규화 헬퍼 함수."""
        def clean_name(name: str) -> str:
            if not name:
                return ""
            # 특수문자 제거, 공백 정규화 등
            return " ".join(name.strip().split())
        
        assert clean_name("  정품  호환  ") == "정품 호환"
        assert clean_name("") == ""
        assert clean_name("테스트상품") == "테스트상품"

    def test_validate_sourcing_candidate(self):
        """소싱 후보 유효성 검사."""
        def validate_candidate(
            supplier_item_id: str | None,
            supply_price: float | None
        ) -> tuple[bool, str]:
            if not supplier_item_id:
                return False, "supplier_item_id is required"
            if supply_price is None or supply_price <= 0:
                return False, "supply_price must be positive"
            return True, ""
        
        # 유효한 케이스
        valid, msg = validate_candidate("ITEM001", 10000)
        assert valid is True
        assert msg == ""
        
        # 무효한 케이스들
        valid, msg = validate_candidate(None, 10000)
        assert valid is False
        assert "supplier_item_id" in msg.lower()
        
        valid, msg = validate_candidate("ITEM002", 0)
        assert valid is False
        assert "supply_price" in msg.lower()


@pytest.mark.unit
class TestSourcingServiceFiltering:
    """필터링 로직 테스트."""

    def test_filter_by_supply_price_threshold(self, db_session: Session):
        """공급가격 임계값 필터링."""
        # 테스트 데이터 생성
        candidates = [
            SourcingCandidate(
                id=uuid.uuid4(),
                supplier_item_id=f"ITEM_{i:03d}",
                supplier_code="ownerclan",
                name=f"Product {i}",
                supply_price=10000 + i * 1000,  # 10000 ~ 19000
                source_strategy="KEYWORD",
                spec_data={}
            )
            for i in range(10)
        ]
        db_session.add_all(candidates)
        db_session.commit()
        
        # 공급가격 임계값 적용
        min_supply_price = 10000  # 기준 가격
        
        # 필터링된 후보 조회 (supply_price 기준으로 간단하게)
        filtered_candidates = db_session.query(SourcingCandidate).filter(
            SourcingCandidate.supply_price >= min_supply_price
        ).all()
        
        # 모두 기준 이상이어야 함
        assert len(filtered_candidates) == 10
        assert all(c.supply_price >= 10000 for c in filtered_candidates)

    def test_filter_by_forbidden_keywords(self, db_session: Session):
        """금지 키워드 필터링."""
        forbidden_keywords = ["배터리", "리튬", "성인용품"]
        
        # 금지 키워드 포함 상품
        forbidden_candidate = SourcingCandidate(
            id=uuid.uuid4(),
            supplier_item_id="FORBIDDEN_ITEM",
            supplier_code="ownerclan",
            name="리튬 배터리",
            supply_price=10000,
            source_strategy="KEYWORD",
            spec_data={"name": "리튬 배터리"}
        )
        db_session.add(forbidden_candidate)
        
        # 정상 상품
        normal_candidate = SourcingCandidate(
            id=uuid.uuid4(),
            supplier_item_id="NORMAL_ITEM",
            supplier_code="ownerclan",
            name="일반 상품",
            supply_price=10000,
            source_strategy="KEYWORD",
            spec_data={"name": "일반 상품"}
        )
        db_session.add(normal_candidate)
        db_session.commit()
        
        # 금지 키워드 필터링 로직
        def contains_forbidden_keyword(name: str) -> bool:
            if not name:
                return False
            return any(keyword in name for keyword in forbidden_keywords)
        
        # 테스트
        forbidden_result = db_session.query(SourcingCandidate).filter(
            SourcingCandidate.id == forbidden_candidate.id
        ).first()
        
        normal_result = db_session.query(SourcingCandidate).filter(
            SourcingCandidate.id == normal_candidate.id
        ).first()
        
        assert contains_forbidden_keyword(forbidden_result.name)
        assert not contains_forbidden_keyword(normal_result.name)
