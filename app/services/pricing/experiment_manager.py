import uuid
import random
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models import PricingExperiment, ProductExperimentMapping, PricingSettings

class ExperimentManager:
    def __init__(self, db: Session):
        self.db = db

    def get_assigned_experiment(self, product_id: uuid.UUID) -> tuple[PricingExperiment | None, str | None]:
        """
        상품에 할당된 현재 실험 및 그룹을 반환합니다.
        """
        stmt = select(ProductExperimentMapping, PricingExperiment).join(
            PricingExperiment, ProductExperimentMapping.experiment_id == PricingExperiment.id
        ).where(
            ProductExperimentMapping.product_id == product_id,
            PricingExperiment.status == "ACTIVE"
        )
        result = self.db.execute(stmt).first()
        if result:
            return result[1], result[0].group
        return None, None

    def assign_experiment_if_needed(self, product_id: uuid.UUID) -> tuple[PricingExperiment | None, str | None]:
        """
        활성화된 실험이 있다면 상품을 해당 실험군에 할당합니다.
        """
        # 1. 이미 할당되었는지 확인
        exp, group = self.get_assigned_experiment(product_id)
        if exp:
            return exp, group

        # 2. 활성 실험 찾기
        stmt = select(PricingExperiment).where(PricingExperiment.status == "ACTIVE").order_by(PricingExperiment.created_at.desc())
        exp = self.db.execute(stmt).scalars().first()
        if not exp:
            return None, None

        # 3. 실험군 할당 결정 (test_ratio 기반)
        if random.random() < exp.test_ratio:
            group = "TEST"
        else:
            group = "CONTROL"

        # 4. 매핑 기록
        mapping = ProductExperimentMapping(
            product_id=product_id,
            experiment_id=exp.id,
            group=group
        )
        self.db.add(mapping)
        self.db.flush()
        
        return exp, group

    def get_effective_policy(self, product_id: uuid.UUID, account_id: uuid.UUID) -> dict:
        """
        대상 상품과 계정에 적용될 최종 정책을 반환합니다.
        """
        # 기본 설정 가져오기
        stmt = select(PricingSettings).where(PricingSettings.market_account_id == account_id)
        settings = self.db.execute(stmt).scalars().first()
        
        policy = {
            "auto_mode": settings.auto_mode if settings else "SHADOW",
            "confidence_threshold": settings.confidence_threshold if settings else 0.95,
            "max_changes_per_hour": settings.max_changes_per_hour if settings else 50,
            "cooldown_hours": settings.cooldown_hours if settings else 24
        }

        # 실험군 여부 확인 및 할당
        exp, group = self.assign_experiment_if_needed(product_id)
        
        # 메타데이터 추가
        policy["experiment_id"] = exp.id if exp else None
        policy["experiment_group"] = group if exp else None

        if exp and group == "TEST" and exp.config_variant:
            # 실험군인 경우 오버라이드
            policy.update(exp.config_variant)
            
        return policy
