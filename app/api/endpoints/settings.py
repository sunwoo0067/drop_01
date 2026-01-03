import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from app.db import get_session
from app.models import (
    APIKey,
    MarketAccount,
    SupplierAccount,
    MarketListing,
    MarketOrderRaw,
    MarketProductRaw,
    Order,
    OrderItem,
    MarketInquiryRaw,
    PricingRecommendation,
    PriceChangeLog,
    PricingSettings,
)
from app.ownerclan_client import OwnerClanClient
from app.settings import settings

router = APIRouter()


def _to_iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.isoformat()


def _mask_secret(value: str | None, keep_start: int = 4, keep_end: int = 4) -> str | None:
    if not value:
        return None

    s = str(value)
    if len(s) <= keep_start + keep_end:
        return "*" * len(s)

    return f"{s[:keep_start]}****{s[-keep_end:]}"


class OwnerClanPrimaryAccountIn(BaseModel):
    user_type: str = "seller"
    username: str
    password: str


class OwnerClanAccountIn(BaseModel):
    user_type: str
    username: str
    password: str
    set_primary: bool = True
    is_active: bool = True


class SupplierConfigIn(BaseModel):
    margin_rate: float = 0.15
    delivery_fee: int = 3000
    sync_auto_enabled: bool = True


@router.get("/suppliers/ownerclan/primary")
def get_ownerclan_primary_account(session: Session = Depends(get_session)) -> dict:
    account = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .filter(SupplierAccount.user_type == "seller")
        .filter(SupplierAccount.is_primary.is_(True))
        .filter(SupplierAccount.is_active.is_(True))
        .one_or_none()
    )

    if not account:
        return {"configured": False, "account": None}

    return {
        "configured": True,
        "account": {
            "id": str(account.id),
            "supplierCode": account.supplier_code,
            "userType": account.user_type,
            "username": account.username,
            "tokenExpiresAt": _to_iso(account.token_expires_at),
            "isPrimary": bool(account.is_primary),
            "isActive": bool(account.is_active),
            "updatedAt": _to_iso(account.updated_at),
        },
    }


@router.post("/suppliers/ownerclan/primary")
def set_ownerclan_primary_account(payload: OwnerClanPrimaryAccountIn, session: Session = Depends(get_session)) -> dict:
    user_type = payload.user_type or settings.ownerclan_primary_user_type
    username = payload.username or settings.ownerclan_primary_username
    password = payload.password or settings.ownerclan_primary_password

    if not username or not password:
        raise HTTPException(status_code=400, detail="오너클랜 대표계정 ID/PW가 필요합니다")

    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
    )

    try:
        token = client.issue_token(username=username, password=password, user_type=user_type)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"오너클랜 토큰 발급 실패: {e}")

    # primary는 user_type 별로 유지합니다(seller/vendor 각각 1개씩 가능)
    session.query(SupplierAccount).filter(SupplierAccount.supplier_code == "ownerclan").filter(SupplierAccount.user_type == user_type).update({"is_primary": False})

    existing = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .filter(SupplierAccount.username == username)
        .one_or_none()
    )

    if existing:
        existing.user_type = user_type
        existing.access_token = token.access_token
        existing.token_expires_at = token.expires_at
        existing.is_primary = True
        existing.is_active = True
        account = existing
    else:
        account = SupplierAccount(
            supplier_code="ownerclan",
            user_type=user_type,
            username=username,
            access_token=token.access_token,
            token_expires_at=token.expires_at,
            is_primary=True,
            is_active=True,
        )
        session.add(account)
        session.flush()

    session.commit()
    return {
        "accountId": str(account.id),
        "username": account.username,
        "tokenExpiresAt": _to_iso(account.token_expires_at),
    }


@router.get("/suppliers/config")
def get_supplier_config(session: Session = Depends(get_session)) -> dict:
    from app.models import SystemSetting
    setting = session.query(SystemSetting).filter_by(key="supplier_config").one_or_none()
    
    if not setting:
        return {
            "margin_rate": settings.pricing_default_margin_rate or 0.15,
            "delivery_fee": 3000,
            "sync_auto_enabled": True
        }
    
    return setting.value


@router.post("/suppliers/config")
def update_supplier_config(payload: SupplierConfigIn, session: Session = Depends(get_session)) -> dict:
    from app.models import SystemSetting
    setting = session.query(SystemSetting).filter_by(key="supplier_config").one_or_none()
    
    if not setting:
        setting = SystemSetting(
            key="supplier_config",
            value=payload.model_dump(),
            description="Global Supplier & Pricing Configuration"
        )
        session.add(setting)
    else:
        setting.value = payload.model_dump()
    
    session.commit()
    return setting.value


@router.get("/suppliers/ownerclan/accounts")
def list_ownerclan_accounts(session: Session = Depends(get_session)) -> list[dict]:
    accounts = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .order_by(SupplierAccount.updated_at.desc())
        .all()
    )

    result: list[dict] = []
    for account in accounts:
        result.append(
            {
                "id": str(account.id),
                "supplierCode": account.supplier_code,
                "userType": account.user_type,
                "username": account.username,
                "tokenExpiresAt": _to_iso(account.token_expires_at),
                "isPrimary": bool(account.is_primary),
                "isActive": bool(account.is_active),
                "updatedAt": _to_iso(account.updated_at),
            }
        )
    return result


@router.post("/suppliers/ownerclan/accounts")
def upsert_ownerclan_account(payload: OwnerClanAccountIn, session: Session = Depends(get_session)) -> dict:
    user_type = str(payload.user_type or "").strip().lower()
    username = str(payload.username or "").strip()
    password = str(payload.password or "")
    set_primary = bool(payload.set_primary)
    is_active = bool(payload.is_active)

    if user_type not in ("seller", "vendor", "supplier"):
        raise HTTPException(status_code=400, detail="user_type은 seller/vendor/supplier 중 하나여야 합니다")
    if not username or not password:
        raise HTTPException(status_code=400, detail="오너클랜 계정 ID/PW가 필요합니다")

    client = OwnerClanClient(
        auth_url=settings.ownerclan_auth_url,
        api_base_url=settings.ownerclan_api_base_url,
        graphql_url=settings.ownerclan_graphql_url,
    )

    try:
        token = client.issue_token(username=username, password=password, user_type=user_type)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"오너클랜 토큰 발급 실패: {e}")

    if set_primary:
        session.query(SupplierAccount).filter(SupplierAccount.supplier_code == "ownerclan").filter(SupplierAccount.user_type == user_type).update({"is_primary": False})

    existing = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
        .filter(SupplierAccount.username == username)
        .one_or_none()
    )

    if existing:
        existing.user_type = user_type
        existing.access_token = token.access_token
        existing.token_expires_at = token.expires_at
        existing.is_primary = set_primary
        existing.is_active = is_active
        account = existing
    else:
        account = SupplierAccount(
            supplier_code="ownerclan",
            user_type=user_type,
            username=username,
            access_token=token.access_token,
            token_expires_at=token.expires_at,
            is_primary=set_primary,
            is_active=is_active,
        )
        session.add(account)
        session.flush()

    session.commit()
    return {
        "accountId": str(account.id),
        "userType": account.user_type,
        "username": account.username,
        "tokenExpiresAt": _to_iso(account.token_expires_at),
        "isPrimary": bool(account.is_primary),
        "isActive": bool(account.is_active),
        "updatedAt": _to_iso(account.updated_at),
    }


class CoupangAccountIn(BaseModel):
    name: str
    vendor_id: str
    vendor_user_id: str = ""
    access_key: str
    secret_key: str
    is_active: bool | None = None


@router.get("/markets/coupang/accounts")
def list_coupang_accounts(session: Session = Depends(get_session)) -> list[dict]:
    stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG").order_by(MarketAccount.created_at.desc())
    accounts = session.scalars(stmt).all()

    result: list[dict] = []
    for account in accounts:
        creds = account.credentials or {}
        result.append(
            {
                "id": str(account.id),
                "marketCode": account.market_code,
                "name": account.name,
                "isActive": bool(account.is_active),
                "vendorId": creds.get("vendor_id") or "",
                "vendorUserId": creds.get("vendor_user_id") or "",
                "accessKeyMasked": _mask_secret(creds.get("access_key")),
                "secretKeyMasked": _mask_secret(creds.get("secret_key")),
                "createdAt": _to_iso(account.created_at),
                "updatedAt": _to_iso(account.updated_at),
            }
        )

    return result


@router.post("/markets/coupang/accounts")
def create_coupang_account(payload: CoupangAccountIn, session: Session = Depends(get_session)) -> dict:
    if not payload.name:
        raise HTTPException(status_code=400, detail="계정 이름이 필요합니다")
    if not payload.vendor_id:
        raise HTTPException(status_code=400, detail="vendorId가 필요합니다")
    if not payload.access_key or not payload.secret_key:
        raise HTTPException(status_code=400, detail="쿠팡 Access Key/Secret Key가 필요합니다")

    should_activate: bool
    if payload.is_active is None:
        has_active = (
            session.query(MarketAccount)
            .filter(MarketAccount.market_code == "COUPANG")
            .filter(MarketAccount.is_active.is_(True))
            .first()
        )
        should_activate = has_active is None
    else:
        should_activate = bool(payload.is_active)

    if should_activate:
        # 다중 계정 지원을 위해 기존 계정 비활성화 로직 제거
        pass

    account = MarketAccount(
        market_code="COUPANG",
        name=payload.name,
        credentials={
            "vendor_id": payload.vendor_id,
            "vendor_user_id": payload.vendor_user_id,
            "access_key": payload.access_key,
            "secret_key": payload.secret_key,
        },
        is_active=should_activate,
    )

    session.add(account)

    session.commit()
    creds = account.credentials or {}
    return {
        "id": str(account.id),
        "marketCode": account.market_code,
        "name": account.name,
        "isActive": bool(account.is_active),
        "vendorId": creds.get("vendor_id") or "",
        "vendorUserId": creds.get("vendor_user_id") or "",
        "accessKeyMasked": _mask_secret(creds.get("access_key")),
        "secretKeyMasked": _mask_secret(creds.get("secret_key")),
        "createdAt": _to_iso(account.created_at),
        "updatedAt": _to_iso(account.updated_at),
    }


class CoupangAccountUpdateIn(BaseModel):
    name: str | None = None
    vendor_id: str | None = None
    vendor_user_id: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    is_active: bool | None = None


@router.patch("/markets/coupang/accounts/{account_id}")
def update_coupang_account(account_id: uuid.UUID, payload: CoupangAccountUpdateIn, session: Session = Depends(get_session)) -> dict:
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "COUPANG":
        raise HTTPException(status_code=404, detail="쿠팡 계정을 찾을 수 없습니다")

    if payload.name is not None:
        if not payload.name:
            raise HTTPException(status_code=400, detail="계정 이름이 필요합니다")
        account.name = payload.name

    creds = dict(account.credentials or {})

    if payload.vendor_id is not None:
        creds["vendor_id"] = payload.vendor_id
    if payload.vendor_user_id is not None:
        creds["vendor_user_id"] = payload.vendor_user_id
    if payload.access_key is not None:
        creds["access_key"] = payload.access_key
    if payload.secret_key is not None:
        creds["secret_key"] = payload.secret_key

    account.credentials = creds

    if payload.is_active is True:
        # 다중 계정 지원을 위해 기존 계정 비활성화 로직 제거
        account.is_active = True
    elif payload.is_active is False:
        account.is_active = False

    try:
        session.commit()
    except IntegrityError:
        raise HTTPException(status_code=400, detail="이미 존재하는 쿠팡 계정 이름입니다")

    return {
        "id": str(account.id),
        "marketCode": account.market_code,
        "name": account.name,
        "isActive": bool(account.is_active),
        "vendorId": creds.get("vendor_id") or "",
        "vendorUserId": creds.get("vendor_user_id") or "",
        "accessKeyMasked": _mask_secret(creds.get("access_key")),
        "secretKeyMasked": _mask_secret(creds.get("secret_key")),
        "createdAt": _to_iso(account.created_at),
        "updatedAt": _to_iso(account.updated_at),
    }


@router.post("/markets/coupang/accounts/{account_id}/activate")
def activate_coupang_account(account_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "COUPANG":
        raise HTTPException(status_code=404, detail="쿠팡 계정을 찾을 수 없습니다")

    # 다중 계정 지원을 위해 기존 계정 비활성화 로직 제거
    account.is_active = True
    session.commit()

    creds = dict(account.credentials or {})
    return {
        "activatedAccountId": str(account.id),
        "account": {
            "id": str(account.id),
            "marketCode": account.market_code,
            "name": account.name,
            "isActive": bool(account.is_active),
            "vendorId": creds.get("vendor_id") or "",
            "vendorUserId": creds.get("vendor_user_id") or "",
            "accessKeyMasked": _mask_secret(creds.get("access_key")),
            "secretKeyMasked": _mask_secret(creds.get("secret_key")),
            "createdAt": _to_iso(account.created_at),
            "updatedAt": _to_iso(account.updated_at),
        },
    }


@router.delete("/markets/coupang/accounts/{account_id}")
def delete_coupang_account(account_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "COUPANG":
        raise HTTPException(status_code=404, detail="쿠팡 계정을 찾을 수 없습니다")

    # 1. OrderItem 중 이 계정의 Listing을 참조하는 항목의 연결 해제
    listing_ids_stmt = select(MarketListing.id).where(MarketListing.market_account_id == account_id)
    listing_ids = session.scalars(listing_ids_stmt).all()
    if listing_ids:
        session.query(OrderItem).filter(OrderItem.market_listing_id.in_(listing_ids)).update({"market_listing_id": None}, synchronize_session=False)

    # 2. Order 중 이 계정의 OrderRaw를 참조하는 항목의 연결 해제
    order_raw_ids_stmt = select(MarketOrderRaw.id).where(MarketOrderRaw.account_id == account_id)
    order_raw_ids = session.scalars(order_raw_ids_stmt).all()
    if order_raw_ids:
        session.query(Order).filter(Order.market_order_id.in_(order_raw_ids)).update({"market_order_id": None}, synchronize_session=False)

    # 3. 연관된 데이터 삭제 (FK 제약 조건 순서 고려 필요할 수 있으나 대부분 MarketAccount 직접 참조)
    session.execute(delete(PricingRecommendation).where(PricingRecommendation.market_account_id == account_id))
    session.execute(delete(PriceChangeLog).where(PriceChangeLog.market_account_id == account_id))
    session.execute(delete(PricingSettings).where(PricingSettings.market_account_id == account_id))
    
    session.execute(delete(MarketListing).where(MarketListing.market_account_id == account_id))
    session.execute(delete(MarketOrderRaw).where(MarketOrderRaw.account_id == account_id))
    session.execute(delete(MarketProductRaw).where(MarketProductRaw.account_id == account_id))
    session.execute(delete(MarketInquiryRaw).where(MarketInquiryRaw.account_id == account_id))

    # 4. 최종적으로 계정 삭제
    session.delete(account)
    session.commit()
    return {"deleted": True, "id": str(account_id)}


class SmartStoreAccountIn(BaseModel):
    name: str
    client_id: str
    client_secret: str
    is_active: bool | None = None


@router.get("/markets/smartstore/accounts")
def list_smartstore_accounts(session: Session = Depends(get_session)) -> list[dict]:
    stmt = select(MarketAccount).where(MarketAccount.market_code == "SMARTSTORE").order_by(MarketAccount.created_at.desc())
    accounts = session.scalars(stmt).all()

    result: list[dict] = []
    for account in accounts:
        creds = account.credentials or {}
        result.append(
            {
                "id": str(account.id),
                "marketCode": account.market_code,
                "name": account.name,
                "isActive": bool(account.is_active),
                "clientIdMasked": _mask_secret(creds.get("client_id")),
                "clientSecretMasked": _mask_secret(creds.get("client_secret")),
                "createdAt": _to_iso(account.created_at),
                "updatedAt": _to_iso(account.updated_at),
            }
        )
    return result


@router.post("/markets/smartstore/accounts")
def create_smartstore_account(payload: SmartStoreAccountIn, session: Session = Depends(get_session)) -> dict:
    if not payload.name:
        raise HTTPException(status_code=400, detail="계정 이름이 필요합니다")
    if not payload.client_id or not payload.client_secret:
        raise HTTPException(status_code=400, detail="스마트스토어 Client ID/Secret이 필요합니다")

    should_activate: bool
    if payload.is_active is None:
        has_active = (
            session.query(MarketAccount)
            .filter(MarketAccount.market_code == "SMARTSTORE")
            .filter(MarketAccount.is_active.is_(True))
            .first()
        )
        should_activate = has_active is None
    else:
        should_activate = bool(payload.is_active)

    if should_activate:
        # 다중 계정 지원을 위해 기존 계정 비활성화 로직 제거
        pass

    account = MarketAccount(
        market_code="SMARTSTORE",
        name=payload.name,
        credentials={
            "client_id": payload.client_id,
            "client_secret": payload.client_secret,
        },
        is_active=should_activate,
    )

    session.add(account)
    try:
        session.commit()
    except IntegrityError:
        raise HTTPException(status_code=400, detail="이미 존재하는 스마트스토어 계정 이름입니다")

    creds = account.credentials or {}
    return {
        "id": str(account.id),
        "marketCode": account.market_code,
        "name": account.name,
        "isActive": bool(account.is_active),
        "clientIdMasked": _mask_secret(creds.get("client_id")),
        "clientSecretMasked": _mask_secret(creds.get("client_secret")),
        "createdAt": _to_iso(account.created_at),
        "updatedAt": _to_iso(account.updated_at),
    }


class SmartStoreAccountUpdateIn(BaseModel):
    name: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    is_active: bool | None = None


@router.patch("/markets/smartstore/accounts/{account_id}")
def update_smartstore_account(account_id: uuid.UUID, payload: SmartStoreAccountUpdateIn, session: Session = Depends(get_session)) -> dict:
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code != "SMARTSTORE":
        raise HTTPException(status_code=404, detail="스마트스토어 계정을 찾을 수 없습니다")

    if payload.name is not None:
        if not payload.name:
            raise HTTPException(status_code=400, detail="계정 이름이 필요합니다")
        account.name = payload.name

    creds = dict(account.credentials or {})
    if payload.client_id is not None:
        creds["client_id"] = payload.client_id
    if payload.client_secret is not None:
        creds["client_secret"] = payload.client_secret
    
    account.credentials = creds

    if payload.is_active is True:
        # 다중 계정 지원을 위해 기존 계정 비활성화 로직 제거
        account.is_active = True
    elif payload.is_active is False:
        account.is_active = False

    try:
        session.commit()
    except IntegrityError:
        raise HTTPException(status_code=400, detail="이미 존재하는 스마트스토어 계정 이름입니다")

    return {
        "id": str(account.id),
        "marketCode": account.market_code,
        "name": account.name,
        "isActive": bool(account.is_active),
        "clientIdMasked": _mask_secret(creds.get("client_id")),
        "clientSecretMasked": _mask_secret(creds.get("client_secret")),
        "createdAt": _to_iso(account.created_at),
        "updatedAt": _to_iso(account.updated_at),
    }


@router.post("/markets/smartstore/accounts/{account_id}/activate")
def activate_smartstore_account(account_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code not in ["SMARTSTORE", "NAVER"]:
        raise HTTPException(status_code=404, detail="스마트스토어 계정을 찾을 수 없습니다")

    # 다중 계정 지원을 위해 기존 계정 비활성화 로직 제거
    account.is_active = True
    session.commit()

    creds = dict(account.credentials or {})
    return {
        "activatedAccountId": str(account.id),
        "account": {
            "id": str(account.id),
            "marketCode": account.market_code,
            "name": account.name,
            "isActive": bool(account.is_active),
            "clientIdMasked": _mask_secret(creds.get("client_id")),
            "clientSecretMasked": _mask_secret(creds.get("client_secret")),
            "createdAt": _to_iso(account.created_at),
            "updatedAt": _to_iso(account.updated_at),
        },
    }


@router.delete("/markets/smartstore/accounts/{account_id}")
def delete_smartstore_account(account_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    account = session.get(MarketAccount, account_id)
    if not account or account.market_code not in ["SMARTSTORE", "NAVER"]:
        raise HTTPException(status_code=404, detail="스마트스토어 계정을 찾을 수 없습니다")

    # 1. OrderItem 중 이 계정의 Listing을 참조하는 항목의 연결 해제
    listing_ids_stmt = select(MarketListing.id).where(MarketListing.market_account_id == account_id)
    listing_ids = session.scalars(listing_ids_stmt).all()
    if listing_ids:
        session.query(OrderItem).filter(OrderItem.market_listing_id.in_(listing_ids)).update({"market_listing_id": None}, synchronize_session=False)

    # 2. Order 중 이 계정의 OrderRaw를 참조하는 항목의 연결 해제
    order_raw_ids_stmt = select(MarketOrderRaw.id).where(MarketOrderRaw.account_id == account_id)
    order_raw_ids = session.scalars(order_raw_ids_stmt).all()
    if order_raw_ids:
        session.query(Order).filter(Order.market_order_id.in_(order_raw_ids)).update({"market_order_id": None}, synchronize_session=False)

    # 3. 연관된 데이터 삭제
    session.execute(delete(PricingRecommendation).where(PricingRecommendation.market_account_id == account_id))
    session.execute(delete(PriceChangeLog).where(PriceChangeLog.market_account_id == account_id))
    session.execute(delete(PricingSettings).where(PricingSettings.market_account_id == account_id))

    session.execute(delete(MarketListing).where(MarketListing.market_account_id == account_id))
    session.execute(delete(MarketOrderRaw).where(MarketOrderRaw.account_id == account_id))
    session.execute(delete(MarketProductRaw).where(MarketProductRaw.account_id == account_id))
    session.execute(delete(MarketInquiryRaw).where(MarketInquiryRaw.account_id == account_id))

    # 4. 최종적으로 계정 삭제
    session.delete(account)
    session.commit()
    return {"deleted": True, "id": str(account_id)}


AIProvider = Literal["openai", "gemini"]


class AIKeyIn(BaseModel):
    provider: AIProvider
    key: str
    is_active: bool = True


@router.get("/ai/keys")
def list_ai_keys(session: Session = Depends(get_session)) -> list[dict]:
    stmt = select(APIKey).order_by(APIKey.created_at.desc())
    keys = session.scalars(stmt).all()

    result: list[dict] = []
    for row in keys:
        result.append(
            {
                "id": str(row.id),
                "provider": row.provider,
                "keyMasked": _mask_secret(row.key),
                "isActive": bool(row.is_active),
                "createdAt": _to_iso(row.created_at),
            }
        )
    return result


@router.post("/ai/keys")
def create_ai_key(payload: AIKeyIn, session: Session = Depends(get_session)) -> dict:
    if not payload.key:
        raise HTTPException(status_code=400, detail="API Key가 필요합니다")

    row = APIKey(provider=str(payload.provider).lower(), key=payload.key, is_active=bool(payload.is_active))
    session.add(row)
    session.commit()

    return {
        "id": str(row.id),
        "provider": row.provider,
        "keyMasked": _mask_secret(row.key),
        "isActive": bool(row.is_active),
        "createdAt": _to_iso(row.created_at),
    }


class AIKeyUpdateIn(BaseModel):
    is_active: bool


@router.patch("/ai/keys/{key_id}")
def update_ai_key(key_id: uuid.UUID, payload: AIKeyUpdateIn, session: Session = Depends(get_session)) -> dict:
    row = session.get(APIKey, key_id)
    if not row:
        raise HTTPException(status_code=404, detail="API Key를 찾을 수 없습니다")

    row.is_active = bool(payload.is_active)
    session.commit()

    return {
        "id": str(row.id),
        "provider": row.provider,
        "keyMasked": _mask_secret(row.key),
        "isActive": bool(row.is_active),
        "createdAt": _to_iso(row.created_at),
    }


@router.delete("/ai/keys/{key_id}")
def delete_ai_key(key_id: uuid.UUID, session: Session = Depends(get_session)) -> dict:
    row = session.get(APIKey, key_id)
    if not row:
        raise HTTPException(status_code=404, detail="API Key를 찾을 수 없습니다")

    session.delete(row)
    session.commit()

    return {"deleted": True, "id": str(key_id)}


class OrchestratorSettingIn(BaseModel):
    listing_limit: int = 15000
    sourcing_keyword_limit: int = 30
    sourcing_import_limit: int = 15000
    initial_processing_batch: int = 100
    processing_batch_size: int = 50
    listing_concurrency: int = 5
    listing_batch_limit: int = 100
    backfill_approve_enabled: bool = True
    backfill_approve_limit: int = 2000
    continuous_mode: bool = False


class LifecycleCriteriaUpdateIn(BaseModel):
    step1_to_step2: dict | None = None
    step2_to_step3: dict | None = None
    category_adjusted: dict | None = None


class LifecycleUiSettingsIn(BaseModel):
    categorySort: dict | None = None
    autoSortEnabled: bool | None = None
    categoryFilter: str | None = None


@router.get("/orchestrator")
def get_orchestrator_settings(session: Session = Depends(get_session)) -> dict:
    from app.models import SystemSetting
    setting = session.query(SystemSetting).filter_by(key="orchestrator").one_or_none()
    
    if not setting:
        # 기본값 반환
        return {
            "listing_limit": 15000,
            "sourcing_keyword_limit": 30,
            "sourcing_import_limit": 15000,
            "initial_processing_batch": 100,
            "processing_batch_size": 50,
            "listing_concurrency": 5,
            "listing_batch_limit": 100,
            "backfill_approve_enabled": True,
            "backfill_approve_limit": 2000,
            "continuous_mode": False
        }
    
    return setting.value


@router.post("/orchestrator")
def update_orchestrator_settings(payload: OrchestratorSettingIn, session: Session = Depends(get_session)) -> dict:
    from app.models import SystemSetting
    setting = session.query(SystemSetting).filter_by(key="orchestrator").one_or_none()
    
    if not setting:
        setting = SystemSetting(
            key="orchestrator",
            value=payload.model_dump(),
            description="Orchestrator Service Configuration"
        )
        session.add(setting)
    else:
        setting.value = payload.model_dump()
    
    session.commit()
    return setting.value


@router.get("/lifecycle-criteria")
def get_lifecycle_criteria(session: Session = Depends(get_session)) -> dict:
    from app.models import SystemSetting
    from app.services.product_lifecycle_service import ProductLifecycleService

    setting = session.query(SystemSetting).filter_by(key="lifecycle_criteria").one_or_none()
    if not setting or not isinstance(setting.value, dict):
        return ProductLifecycleService.default_criteria()
    return setting.value


@router.post("/lifecycle-criteria")
def update_lifecycle_criteria(payload: LifecycleCriteriaUpdateIn, session: Session = Depends(get_session)) -> dict:
    from app.models import SystemSetting
    from app.services.product_lifecycle_service import ProductLifecycleService

    default_criteria = ProductLifecycleService.default_criteria()
    setting = session.query(SystemSetting).filter_by(key="lifecycle_criteria").one_or_none()
    current = setting.value if setting and isinstance(setting.value, dict) else default_criteria

    updated = {
        "step1_to_step2": {
            **default_criteria["step1_to_step2"],
            **(current.get("step1_to_step2") or {}),
            **(payload.step1_to_step2 or {}),
        },
        "step2_to_step3": {
            **default_criteria["step2_to_step3"],
            **(current.get("step2_to_step3") or {}),
            **(payload.step2_to_step3 or {}),
        },
        "category_adjusted": {
            **default_criteria["category_adjusted"],
            **(current.get("category_adjusted") or {}),
            **(payload.category_adjusted or {}),
        },
    }

    if not setting:
        setting = SystemSetting(
            key="lifecycle_criteria",
            value=updated,
            description="Product lifecycle transition criteria"
        )
        session.add(setting)
    else:
        setting.value = updated

    session.commit()
    return updated


@router.get("/lifecycle-ui")
def get_lifecycle_ui_settings(session: Session = Depends(get_session)) -> dict:
    from app.models import SystemSetting
    setting = session.query(SystemSetting).filter_by(key="lifecycle_ui").one_or_none()
    return setting.value if setting and isinstance(setting.value, dict) else {}


@router.post("/lifecycle-ui")
def update_lifecycle_ui_settings(payload: LifecycleUiSettingsIn, session: Session = Depends(get_session)) -> dict:
    from app.models import SystemSetting
    setting = session.query(SystemSetting).filter_by(key="lifecycle_ui").one_or_none()
    value = {
        "categorySort": payload.categorySort or {},
        "autoSortEnabled": bool(payload.autoSortEnabled) if payload.autoSortEnabled is not None else False,
        "categoryFilter": payload.categoryFilter or ""
    }
    if not setting:
        setting = SystemSetting(
            key="lifecycle_ui",
            value=value,
            description="Lifecycle UI preferences"
        )
        session.add(setting)
    else:
        setting.value = value
    session.commit()
    return setting.value
