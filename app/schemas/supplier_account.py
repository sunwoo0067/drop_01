"""
공급사 계정 관련 응답 스키마.
"""

from pydantic import BaseModel
from datetime import datetime


class OwnerClanPrimaryAccountResult(BaseModel):
    """
    오너클랜 대표계정 설정 결과 표준 응답.
    """
    account_id: str
    username: str
    token_expires_at: str | None
    is_primary: bool = True
    is_active: bool = True


class SupplierAccountError(BaseModel):
    """
    표준 에러 응답.
    """
    error_type: str  # "token_issue_failed", "db_error", "validation_error", "account_not_found"
    message: str
    details: dict | None = None


class SupplierAccountMasked(BaseModel):
    """
    마스킹된 계정 정보 응답.
    """
    id: str
    supplier_code: str
    user_type: str
    username: str
    token_expires_at: str | None
    is_primary: bool
    is_active: bool
    created_at: str
    updated_at: str


class TokenRefreshResult(BaseModel):
    """
    토큰 갱신 결과.
    """
    success: bool
    token_expires_at: str | None
    error_message: str | None = None
