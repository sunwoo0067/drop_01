from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import uuid

from app.db import get_session
from app.services.analytics.coupang_policy import CoupangSourcingPolicyService

router = APIRouter()

class PolicyFeedbackRequest(BaseModel):
    category_code: Optional[str] = None
    keyword: Optional[str] = None
    signal: str # "UP" or "DOWN"
    reason: Optional[str] = None

@router.post("/policy")
async def record_policy_feedback(
    request: PolicyFeedbackRequest,
    db: Session = Depends(get_session)
):
    """
    운영자의 피드백을 기록하여 정책 엔진에 반영합니다. (Human-in-the-loop)
    """
    if not request.category_code and not request.keyword:
        raise HTTPException(status_code=400, detail="category_code 또는 keyword 중 하나는 필수입니다.")
    
    event_type = f"OPERATOR_{request.signal}"
    multiplier = 1.2 if request.signal == "UP" else 0.8
    
    CoupangSourcingPolicyService.log_policy_event(
        session=db,
        category_code=request.category_code,
        event_type=event_type,
        multiplier=multiplier,
        reason=request.reason or "운영자 수동 피드백",
        severity="NONE",
        context={"keyword": request.keyword, "manual_signal": request.signal}
    )
    db.commit()
    
    return {
        "status": "success",
        "message": f"운영자 피드백({request.signal})이 반영되었습니다.",
        "multiplier": multiplier
    }
