"""
공급사 계정 관리 서비스.

공급사 계정(OwnerClan, SmartStore 등)의 CRUD와 인증 로직을 담당합니다.
"""

from typing import Optional
from sqlalchemy.orm import Session
from app.models import SupplierAccount
from app.ownerclan_client import OwnerClanClient, OwnerClanToken
from app.settings import settings
import logging

logger = logging.getLogger(__name__)


class SupplierAccountService:
    """공급사 계정 관리 서비스."""
    
    @staticmethod
    def mask_sensitive_value(value: Optional[str], keep_start: int = 4, keep_end: int = 4) -> Optional[str]:
        """
        민감정보 마스킹.
        
        Args:
            value: 마스킹할 값
            keep_start: 앞부분 보존할 길이 (기본값 4)
            keep_end: 뒤부분 보존할 길이 (기본값 4)
        
        Returns:
            마스킹된 값 또는 None
        """
        if not value:
            return None
        
        s = str(value)
        if len(s) <= keep_start + keep_end:
            return "*" * len(s)
        
        return f"{s[:keep_start]}****{s[-keep_end:]}"
    
    @staticmethod
    def set_ownerclan_primary_account(
        session: Session,
        user_type: str,
        username: str,
        password: str
    ) -> SupplierAccount:
        """
        오너클랜 대표계정 설정.
        
        토큰 발급 + DB 업데이트를 원자적으로 수행합니다.
        
        Args:
            session: DB 세션
            user_type: 사용자 타입 (seller/vendor/supplier)
            username: 오너클랜 아이디
            password: 오너클랜 비밀번호
        
        Returns:
            생성/업데이트된 SupplierAccount 객체
        
        Raises:
            ValueError: 입력값 누락
            RuntimeError: 토큰 발급 실패
        """
        # 1. 입력 검증
        if not username or not password:
            raise ValueError("오너클랜 대표계정 ID/PW가 필요합니다")
        
        if user_type not in ("seller", "vendor", "supplier"):
            raise ValueError(f"지원하지 않는 user_type입니다: {user_type}")
        
        # 2. 토큰 발급 (외부 API)
        # 민감정보(password)는 로그에 남기지 않음
        try:
            client = OwnerClanClient(
                auth_url=settings.ownerclan_auth_url,
                api_base_url=settings.ownerclan_api_base_url,
                graphql_url=settings.ownerclan_graphql_url,
            )
            token = client.issue_token(
                username=username,
                password=password,
                user_type=user_type
            )
        except Exception as e:
            logger.error(f"오너클랜 토큰 발급 실패: {e}")
            raise RuntimeError(f"오너클랜 토큰 발급 실패: {e}")
        
        # 3. DB 업데이트 (원자성 보장)
        # 같은 user_type의 기존 primary 계정을 비활성화
        session.query(SupplierAccount)\
            .filter(SupplierAccount.supplier_code == "ownerclan")\
            .filter(SupplierAccount.user_type == user_type)\
            .filter(SupplierAccount.is_primary.is_(True))\
            .update({"is_primary": False})
        
        # 계정 upsert (기존 계정이면 업데이트, 없으면 생성)
        existing = session.query(SupplierAccount)\
            .filter(supplierAccount.supplier_code == "ownerclan")\
            .filter(supplierAccount.username == username)\
            .one_or_none()
        
        if existing:
            # 기존 계정 업데이트
            existing.user_type = user_type
            existing.access_token = token.access_token
            existing.token_expires_at = token.expires_at
            existing.is_primary = True
            existing.is_active = True
            account = existing
        else:
            # 신규 계정 생성
            account = supplierAccount(
                supplier_code="ownerclan",
                user_type=user_type,
                username=username,
                access_token=token.access_token,
                token_expires_at=token.expires_at,
                is_primary=True,
                is_active=True,
            )
            session.add(account)
        
        session.flush()  # commit은 caller에서 담당
        
        logger.info(
            f"오너클랜 대표계정 설정 완료: {username} (type={user_type}, "
            f"token_expires={token.expires_at.isoformat() if token.expires_at else 'N/A'})"
        )
        
        return account
    
    @staticmethod
    def refresh_ownerclan_token(
        session: Session,
        account_id,
        force: bool = False
    ) -> Optional[OwnerClanToken]:
        """
        오너클랜 토큰 갱신.
        
        Args:
            session: DB 세션
            account_id: 갱신할 계정 ID
            force: 만료 여부와 상관없이 강제 갱신
        
        Returns:
            갱신된 토큰 또는 None (실패 시)
        """
        account = session.query(supplierAccount).filter(
            supplierAccount.id == account_id
        ).one_or_none()
        
        if not account:
            logger.error(f"계정을 찾을 수 없음: {account_id}")
            return None
        
        if not account.is_active:
            logger.warning(f"비활성 계정은 토큰 갱신 건너뜀: {account_id}")
            return None
        
        # 만료 여부 확인
        needs_refresh = force
        if account.token_expires_at:
            from datetime import datetime, timezone
            # 1시간 전 만료 시 갱신
            needs_refresh = needs_refresh or (
                datetime.now(timezone.utc) >= 
                account.token_expires_at.replace(tzinfo=timezone.utc) - timedelta(hours=1)
            )
        
        if not needs_refresh:
            logger.info(f"토큰 갱신 불필요: {account_id}")
            return None
        
        # 토큰 갱신
        try:
            client = OwnerClanClient(
                auth_url=settings.ownerclan_auth_url,
                api_base_url=settings.ownerclan_api_base_url,
                graphql_url=settings.ownerclan_graphql_url,
                access_token=account.access_token,  # 기존 토큰 사용 가능하면
            )
            
            # refresh_token 메소드가 있다면 사용, 아니면 issue_token 재사용
            if hasattr(client, 'refresh_token'):
                token = client.refresh_token()
            else:
                token = client.issue_token(
                    username=account.username,
                    password=None,  # password는 알 수 없음
                    user_type=account.user_type
                )
            
            account.access_token = token.access_token
            account.token_expires_at = token.expires_at
            session.flush()
            
            logger.info(f"토큰 갱신 완료: {account_id}")
            return token
            
        except Exception as e:
            logger.error(f"토큰 갱신 실패: {account_id}: {e}")
            return None
