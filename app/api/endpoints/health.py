from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text, func
import logging

from app.db import get_session
from app.models import MarketAccount
from app.coupang_client import CoupangClient

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/system")
async def get_system_health(session: Session = Depends(get_session)):
    """
    백엔드 서버 및 데이터베이스 연결 상태를 확인합니다.
    """
    db_ok = False
    now = None
    try:
        # 특정 베이스에 바인딩된 테이블을 통해 쿼리하여 UnboundExecutionError 회피
        now = session.query(func.now()).select_from(MarketAccount).limit(1).scalar()
        db_ok = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")

    return {
        "status": "healthy" if db_ok else "unhealthy",
        "database": "ok" if db_ok else "error",
        "timestamp": now.isoformat() if now else None
    }

@router.get("/accounts")
async def get_accounts_health(session: Session = Depends(get_session)):
    """
    각 마켓 계정의 API 연결 상태를 가볍게 체크합니다.
    """
    accounts = session.query(MarketAccount).filter(MarketAccount.is_active == True).all()
    results = []

    for acc in accounts:
        status = "unknown"
        message = ""
        
        try:
            if acc.market_code == "COUPANG":
                creds = acc.credentials or {}
                client = CoupangClient(
                    access_key=creds.get("access_key", ""),
                    secret_key=creds.get("secret_key", ""),
                    vendor_id=creds.get("vendor_id", "")
                )
                # 가벼운 API 호출로 토큰/인증 유효성 확인
                code, data = client.check_auto_category_agreed()
                if 200 <= code < 300:
                    status = "healthy"
                else:
                    status = "unhealthy"
                    message = data.get("message", "Coupang API error")
            else:
                # 기타 마켓 (SmartStore 등) 추후 확장 가능
                status = "healthy" 
        except Exception as e:
            status = "error"
            message = str(e)
            
        results.append({
            "account_id": str(acc.id),
            "account_name": acc.name,
            "market_code": acc.market_code,
            "status": status,
            "message": message
        })

    return results
