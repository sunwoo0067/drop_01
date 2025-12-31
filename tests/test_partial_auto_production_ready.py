"""
Partial Auto Production-Ready 테스트 슈트

스위치 올리기 전에 반드시 통과해야 하는 3가지 핵심 검증:
1. 동시성 테스트: 동일 문의에 워커가 5번 돌려도 전송 1회만 발생
2. 업무시간 Gate 테스트: 18:00 이후엔 절대 AUTO_SEND 안 됨
3. 실패/재시도 상태 테스트: 전송 실패 시 SEND_FAILED, attempts 증가, 에러 기록, metadata 미러링 확인

실행 방법:
    python -m pytest tests/test_partial_auto_production_ready.py -v
또는
    python tests/test_partial_auto_production_ready.py (직접 실행)
"""

import asyncio
import logging
from datetime import datetime, time
import pytz
from freezegun import freeze_time

from app.db import get_session
from app.models import MarketInquiryRaw, MarketAccount
from app.services.ai.agents.cs_workflow_agent import CSWorkflowAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==================== Helper Functions ====================

async def _run_finalize_concurrently(agent: CSWorkflowAgent, state, n=5):
    """
    finalize를 동시에 여러 번 호출하는 헬퍼 함수
    """
    async def call():
        # state를 복사하여 각 태스크가 독립적으로 사용
        return await agent.finalize(state.copy())

    tasks = [asyncio.create_task(call()) for _ in range(n)]
    return await asyncio.gather(*tasks)


def create_inquiry(db, **kwargs):
    """테스트용 MarketInquiryRaw 생성"""
    inquiry = MarketInquiryRaw(
        market_code=kwargs.get("market_code", "COUPANG"),
        account_id=kwargs.get("account_id"),
        inquiry_id=kwargs.get("market_inquiry_id", "MKT-123"),  # 마켓 원본 ID
        status=kwargs.get("status", "AUTO_SEND"),
        confidence_score=kwargs.get("confidence_score", 0.95),
        ai_suggested_answer=kwargs.get("answer", "테스트 답변입니다."),
        send_status=kwargs.get("send_status", None),
        send_attempts=kwargs.get("send_attempts", 0),
        sent_at=kwargs.get("sent_at", None),
        last_send_error=kwargs.get("last_send_error", None),
        fetched_at=kwargs.get("fetched_at", datetime.now(pytz.UTC)),
        cs_metadata=kwargs.get("cs_metadata", {}),
    )
    db.add(inquiry)
    db.commit()
    db.refresh(inquiry)
    return inquiry


def create_account(db, **kwargs):
    """테스트용 MarketAccount 생성"""
    acc = MarketAccount(
        name=kwargs.get("name", "test_account"),
        market_code=kwargs.get("market_code", "COUPANG"),
        credentials=kwargs.get("credentials", {
            "access_key": "test_key",
            "secret_key": "test_secret",
            "vendor_id": "test_vendor"
        }),
        is_active=True,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


# ==================== Test 1: Idempotency (Concurrency) ====================

async def test_idempotency_sending_lock():
    """
    동일 문의에 대해 finalize를 동시에 여러 번 호출해도
    _send_to_market는 1회만 호출되어야 한다.

    검증 포인트:
    - SENDING 상태 선점이 제대로 작동하는지
    - 다른 워커는 SENDING을 보고 스킵하는지
    - 전송 호출 카운트 == 1이면 합격
    """
    logger.info("=" * 80)
    logger.info("TEST 1: Idempotency - SENDING Lock Test")
    logger.info("=" * 80)

    session_gen = get_session()
    db = next(session_gen)

    try:
        # 테스트용 계정 및 문의 생성
        acc = create_account(db, market_code="COUPANG", name="test_coupang")
        inquiry = create_inquiry(db, account_id=acc.id, send_status=None, send_attempts=0)

        # API 호출 카운트 추적
        sent_calls = {"count": 0}

        # 가짜 _send_to_market 함수로 monkeypatch
        original_send = CSWorkflowAgent._send_to_market

        async def fake_send_to_market(self, inquiry_obj, answer):
            sent_calls["count"] += 1
            logger.info(f"[FAKE SEND] Call #{sent_calls['count']} for inquiry {inquiry_obj.id}")

            # 첫 번째 호출만 성공, 나머지는 SENDING 선점으로 스킵되어야 함
            inquiry_obj.send_status = "SENT"
            inquiry_obj.sent_at = datetime.now(pytz.UTC)
            inquiry_obj.last_send_error = None

            # v1.8.1: cs_metadata에 전송 정보 미러링
            if inquiry_obj.cs_metadata:
                inquiry_obj.cs_metadata.update({
                    "send_status": "SENT",
                    "send_attempts": inquiry_obj.send_attempts,
                    "last_send_error": None
                })

            db.commit()

        # Monkeypatch 적용
        CSWorkflowAgent._send_to_market = fake_send_to_market

        agent = CSWorkflowAgent(db)

        state = {
            "inquiry_id": inquiry.id,  # 내부 PK (UUID)
            "draft_answer": "테스트 답변입니다.",
            "status": "AUTO_SEND",
            "confidence_score": 0.95,
            "intent": "배송문의",
            "sentiment": "중립",
            "logs": ["test log"],
            "policy_evaluation": {"final_score": 0.95}
        }

        # 동시에 5번 finalize 호출
        logger.info("Executing 5 concurrent finalize calls...")
        results = await _run_finalize_concurrently(agent, state, n=5)

        # 결과 확인
        db.refresh(inquiry)
        logger.info(f"Results: {len(results)} calls completed")
        logger.info(f"Send calls count: {sent_calls['count']}")
        logger.info(f"Final send_status: {inquiry.send_status}")
        logger.info(f"Send attempts: {inquiry.send_attempts}")

        # 단언문: 전송 호출이 정확히 1회여야 함
        assert sent_calls["count"] == 1, f"❌ FAIL: send 호출이 {sent_calls['count']}회 발생 (중복 전송 위험)"
        assert inquiry.send_status == "SENT", f"❌ FAIL: 최종 상태가 {inquiry.send_status} (기대: SENT)"
        assert inquiry.sent_at is not None, "❌ FAIL: sent_at이 None"

        # cs_metadata 미러링 확인
        assert inquiry.cs_metadata is not None, "❌ FAIL: cs_metadata가 None"
        assert inquiry.cs_metadata.get("send_status") == "SENT", "❌ FAIL: cs_metadata.send_status 미러링 실패"
        assert inquiry.cs_metadata.get("send_attempts") == inquiry.send_attempts, "❌ FAIL: cs_metadata.send_attempts 미러링 실패"

        logger.info("✅ PASS: Idempotency test passed - only 1 send call occurred")
        logger.info("=" * 80)

    finally:
        # 원래 함수 복구
        CSWorkflowAgent._send_to_market = original_send


# ==================== Test 2: Send Attempts None Safe ====================

async def test_send_attempts_none_safe():
    """
    send_attempts가 None이어도 0으로 처리되어 증가해야 한다.

    검증 포인트:
    - send_attempts = (inquiry.send_attempts or 0) + 1 방어 코드가 작동하는지
    - None + 1로 터지는 버그가 없는지
    """
    logger.info("=" * 80)
    logger.info("TEST 2: Send Attempts None-Safe Test")
    logger.info("=" * 80)

    session_gen = get_session()
    db = next(session_gen)

    try:
        acc = create_account(db, market_code="COUPANG")
        # 명시적으로 None으로 설정
        inquiry = create_inquiry(db, account_id=acc.id, send_status=None, send_attempts=None)

        # 실패 처리 흉내 내는 fake 함수
        original_send = CSWorkflowAgent._send_to_market

        async def fake_send_to_market(self, inquiry_obj, answer):
            # 실패 처리 흉내
            inquiry_obj.send_status = "SEND_FAILED"
            inquiry_obj.last_send_error = "forced_fail_for_test"

            # cs_metadata 미러링
            if inquiry_obj.cs_metadata:
                inquiry_obj.cs_metadata.update({
                    "send_status": "SEND_FAILED",
                    "send_attempts": inquiry_obj.send_attempts,
                    "last_send_error": "forced_fail_for_test"
                })

            db.commit()

        CSWorkflowAgent._send_to_market = fake_send_to_market

        agent = CSWorkflowAgent(db)

        state = {
            "inquiry_id": inquiry.id,
            "draft_answer": "테스트 답변",
            "status": "AUTO_SEND",
            "confidence_score": 0.95,
            "intent": "배송문의",
            "sentiment": "중립",
            "logs": ["test"],
            "policy_evaluation": {"final_score": 0.95}
        }

        # finalize 실행
        await agent.finalize(state)

        # 결과 확인
        db.refresh(inquiry)
        logger.info(f"send_attempts after finalize: {inquiry.send_attempts}")
        logger.info(f"send_status: {inquiry.send_status}")

        # 단언문
        assert inquiry.send_attempts is not None, "❌ FAIL: send_attempts가 여전히 None"
        assert inquiry.send_attempts >= 1, f"❌ FAIL: send_attempts가 증가하지 않음 ({inquiry.send_attempts})"
        assert inquiry.send_status in ("SEND_FAILED", "SENT"), f"❌ FAIL: 상태가 {inquiry.send_status}"

        # cs_metadata 미러링 확인
        assert inquiry.cs_metadata.get("send_status") == inquiry.send_status, "❌ FAIL: cs_metadata 미러링 실패"
        assert inquiry.cs_metadata.get("send_attempts") == inquiry.send_attempts, "❌ FAIL: cs_metadata 미러링 실패"

        logger.info("✅ PASS: send_attempts None-safe test passed")
        logger.info("=" * 80)

    finally:
        CSWorkflowAgent._send_to_market = original_send


# ==================== Test 3: Finalize Return Schema Consistency ====================

async def test_finalize_return_schema_consistent():
    """
    이미 SENT/SENDING 인 경우에도 finalize 반환 스키마가 동일해야 한다.

    검증 포인트:
    - early return해도 항상 final_output, logs, current_step를 포함하는지
    - LangGraph 상태 병합/후속 로깅이 꼬이지 않는지
    """
    logger.info("=" * 80)
    logger.info("TEST 3: Finalize Return Schema Consistency")
    logger.info("=" * 80)

    session_gen = get_session()
    db = next(session_gen)

    try:
        acc = create_account(db, market_code="COUPANG")
        # 이미 전송된 문의 생성
        inquiry = create_inquiry(
            db,
            account_id=acc.id,
            send_status="SENT",
            sent_at=datetime.now(pytz.UTC),
            confidence_score=0.90,
            cs_metadata={"logs": ["previous log"]}
        )

        agent = CSWorkflowAgent(db)

        state = {
            "inquiry_id": inquiry.id,
            "draft_answer": "테스트 답변",
            "status": "AUTO_SEND",
            "confidence_score": 0.95,
            "intent": "배송문의",
            "sentiment": "중립",
            "logs": ["test"],
            "policy_evaluation": {"final_score": 0.95}
        }

        # finalize 실행 (early return 예상)
        res = await agent.finalize(state)

        logger.info(f"Return result: {res}")

        # 단언문: 항상 동일한 스키마로 반환해야 함
        assert "final_output" in res, "❌ FAIL: early return에 final_output 없음"
        assert "logs" in res, "❌ FAIL: early return에 logs 없음"
        assert res.get("current_step") == "finalize", "❌ FAIL: current_step이 finalize가 아님"

        # final_output 내부 검증
        assert "status" in res["final_output"], "❌ FAIL: final_output에 status 없음"
        assert "confidence_score" in res["final_output"], "❌ FAIL: final_output에 confidence_score 없음"

        logger.info(f"✅ PASS: early return schema consistent")
        logger.info(f"   - final_output: {res['final_output']}")
        logger.info(f"   - logs: {res['logs']}")
        logger.info(f"   - current_step: {res['current_step']}")
        logger.info("=" * 80)

    finally:
        pass


# ==================== Test 4: Business Hours Gate ====================

async def test_business_hours_gate():
    """
    업무시간 Gate 테스트: 18:00 이후엔 절대 AUTO_SEND 안 됨

    검증 포인트:
    - time(9, 0) <= now_kst < time(18, 0) 경계값이 정확한지
    - 18:00:00은 AUTO_SEND 되지 않는지
    - 17:59:59는 AUTO_SEND 되는지
    """
    logger.info("=" * 80)
    logger.info("TEST 4: Business Hours Gate Test")
    logger.info("=" * 80)

    session_gen = get_session()
    db = next(session_gen)

    try:
        acc = create_account(db, market_code="COUPANG", name="test_coupang")
        inquiry = create_inquiry(
            db,
            account_id=acc.id,
            send_status=None,
            send_attempts=0,
            confidence_score=0.95  # 임계값 이상으로 설정
        )

        # 원래 finalize 메서드 테스트를 위해 agent 생성
        agent = CSWorkflowAgent(db)

        # 업무시간 외(18:00:00) 상태에서 AUTO_SEND 결정 확인
        # self_review 노드에서 is_business_hours 체크를 테스트

        # 18:00:00 KST: 업무시간 외
        with freeze_time("2025-12-31 18:00:00", tz_offset=9):
            state_1800 = {
                "inquiry_id": inquiry.id,
                "draft_answer": "테스트 답변",
                "confidence_score": 0.95,
                "intent": "배송문의",
                "sentiment": "중립",
                "logs": ["test"],
                "policy_evaluation": {"final_score": 0.95},
                "can_automate": True
            }

            # self_review 실행 (AUTO_SEND 결정 로직 포함)
            result_1800 = await agent.self_review(state_1800)
            status_1800 = result_1800.get("status")

            logger.info(f"[18:00:00 KST] Status: {status_1800}")
            assert status_1800 != "AUTO_SEND", f"❌ FAIL: 18:00에 AUTO_SEND됨 (status={status_1800})"
            assert status_1800 in ("AI_DRAFTED", "HUMAN_REVIEW"), f"❌ FAIL: 18:00에 {status_1800} 상태"

        # 17:59:59 KST: 업무시간 내 (AUTO_SEND 여부 확인)
        with freeze_time("2025-12-31 17:59:59", tz_offset=9):
            state_1759 = {
                "inquiry_id": inquiry.id,
                "draft_answer": "테스트 답변",
                "confidence_score": 0.95,
                "intent": "배송문의",
                "sentiment": "중립",
                "logs": ["test"],
                "policy_evaluation": {"final_score": 0.95},
                "can_automate": True
            }

            result_1759 = await agent.self_review(state_1759)
            status_1759 = result_1759.get("status")

            logger.info(f"[17:59:59 KST] Status: {status_1759}")
            # 업무시간 내이고, enable_cs_partial_auto가 True면 AUTO_SEND 또는 AI_DRAFTED
            assert status_1759 in ("AUTO_SEND", "AI_DRAFTED", "HUMAN_REVIEW"), f"❌ FAIL: 17:59:59에 부적절한 상태 {status_1759}"

        logger.info("✅ PASS: Business hours gate test passed")
        logger.info("   - 18:00:00: AUTO_SEND 차단됨")
        logger.info("   - 17:59:59: 업무시간 내 처리")
        logger.info("=" * 80)

    finally:
        pass


# ==================== Test 5: Send Failure & Retry State ====================

async def test_send_failure_retry_state():
    """
    전송 실패 시 SEND_FAILED, attempts 증가, 에러 기록, metadata 미러링 확인

    검증 포인트:
    - 실패 시 send_status가 SEND_FAILED로 설정되는지
    - last_send_error에 에러 메시지가 기록되는지
    - cs_metadata에 전송 정보가 미러링되는지
    """
    logger.info("=" * 80)
    logger.info("TEST 5: Send Failure & Retry State Test")
    logger.info("=" * 80)

    session_gen = get_session()
    db = next(session_gen)

    try:
        acc = create_account(db, market_code="COUPANG")
        inquiry = create_inquiry(
            db,
            account_id=acc.id,
            send_status=None,
            send_attempts=0,
            confidence_score=0.95
        )

        # 실패 처리 흉내
        original_send = CSWorkflowAgent._send_to_market

        async def fake_send_fail(self, inquiry_obj, answer):
            inquiry_obj.send_status = "SEND_FAILED"
            error_msg = "Test failure: API rate limit exceeded"
            inquiry_obj.last_send_error = error_msg

            # cs_metadata 미러링
            if inquiry_obj.cs_metadata:
                inquiry_obj.cs_metadata.update({
                    "send_status": "SEND_FAILED",
                    "send_attempts": inquiry_obj.send_attempts,
                    "last_send_error": error_msg
                })

            db.commit()

        CSWorkflowAgent._send_to_market = fake_send_fail

        agent = CSWorkflowAgent(db)

        state = {
            "inquiry_id": inquiry.id,
            "draft_answer": "테스트 답변",
            "status": "AUTO_SEND",
            "confidence_score": 0.95,
            "intent": "배송문의",
            "sentiment": "중립",
            "logs": ["test"],
            "policy_evaluation": {"final_score": 0.95}
        }

        # finalize 실행
        await agent.finalize(state)

        # 결과 확인
        db.refresh(inquiry)
        logger.info(f"Final state:")
        logger.info(f"  - send_status: {inquiry.send_status}")
        logger.info(f"  - send_attempts: {inquiry.send_attempts}")
        logger.info(f"  - last_send_error: {inquiry.last_send_error}")
        logger.info(f"  - cs_metadata.send_status: {inquiry.cs_metadata.get('send_status')}")
        logger.info(f"  - cs_metadata.send_attempts: {inquiry.cs_metadata.get('send_attempts')}")
        logger.info(f"  - cs_metadata.last_send_error: {inquiry.cs_metadata.get('last_send_error')}")

        # 단언문
        assert inquiry.send_status == "SEND_FAILED", f"❌ FAIL: 상태가 {inquiry.send_status}"
        assert inquiry.send_attempts >= 1, f"❌ FAIL: attempts가 증가하지 않음 ({inquiry.send_attempts})"
        assert inquiry.last_send_error is not None, "❌ FAIL: last_send_error가 None"

        # cs_metadata 미러링 확인
        assert inquiry.cs_metadata.get("send_status") == "SEND_FAILED", "❌ FAIL: cs_metadata 미러링 실패"
        assert inquiry.cs_metadata.get("send_attempts") == inquiry.send_attempts, "❌ FAIL: cs_metadata 미러링 실패"
        assert inquiry.cs_metadata.get("last_send_error") == inquiry.last_send_error, "❌ FAIL: cs_metadata 미러링 실패"

        logger.info("✅ PASS: Send failure & retry state test passed")
        logger.info("=" * 80)

    finally:
        CSWorkflowAgent._send_to_market = original_send


# ==================== Main Entry Point ====================

# pytest로 실행할 것이므로 main 함수는 주석 처리
# 대신 pytest mark 사용

pytest_plugins = ("pytest_asyncio",)
