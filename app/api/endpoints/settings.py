import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_session
from app.models import APIKey, MarketAccount, SupplierAccount
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


@router.get("/suppliers/ownerclan/primary")
def get_ownerclan_primary_account(session: Session = Depends(get_session)) -> dict:
    account = (
        session.query(SupplierAccount)
        .filter(SupplierAccount.supplier_code == "ownerclan")
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

    session.query(SupplierAccount).filter(SupplierAccount.supplier_code == "ownerclan").update({"is_primary": False})

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

    return {
        "accountId": str(account.id),
        "username": account.username,
        "tokenExpiresAt": _to_iso(account.token_expires_at),
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
        session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").update({"is_active": False})

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

    try:
        session.flush()
    except IntegrityError:
        raise HTTPException(status_code=400, detail="이미 존재하는 쿠팡 계정 이름입니다")

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
        session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").update({"is_active": False})
        account.is_active = True
    elif payload.is_active is False:
        account.is_active = False

    try:
        session.flush()
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

    session.query(MarketAccount).filter(MarketAccount.market_code == "COUPANG").update({"is_active": False})
    account.is_active = True
    session.flush()

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
    session.flush()

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
    session.flush()

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
    session.flush()

    return {"deleted": True, "id": str(key_id)}
