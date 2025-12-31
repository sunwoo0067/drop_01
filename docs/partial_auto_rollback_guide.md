# Partial Auto - 계정별 단계적 해금 가이드

## 📋 목적

Production-Ready 코드(SENDED 선점, None 방어, 스키마 통일 등)가 완료된 상태에서,
실제 운영 전환 시 사고율을 최소화하기 위한 단계적 해금 절차를 설명합니다.

## 🎯 Phase 1: 사전 체크 (스위치 올리기 전)

### 1.1 테스트 통과 확인

```bash
# 모든 Production-Ready 테스트 통과
python tests/test_partial_auto_production_ready.py
```

**기대 결과:**
- ✅ Test 1: Idempotency - SENDING Lock (PASS)
- ✅ Test 2: Send Attempts None-Safe (PASS)
- ✅ Test 3: Finalize Return Schema Consistency (PASS)
- ✅ Test 4: Business Hours Gate (PASS)
- ✅ Test 5: Send Failure & Retry State (PASS)

### 1.2 Shadow Mode 데이터 확인

```sql
-- 최근 7일간 Shadow Mode 통과 통계
SELECT
    DATE(created_at) as date,
    COUNT(*) as total_inquiries,
    SUM(CASE WHEN status = 'AUTO_SEND' THEN 1 ELSE 0 END) as auto_send_count,
    SUM(CASE WHEN status = 'AUTO_SEND' THEN 1 ELSE 0 END)::float / COUNT(*) * 100 as auto_rate
FROM market_inquiry_raw
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

**기준:**
- 일평균 AUTO_SEND 후보가 10건 이상: ✅ 해금 준비 완료
- 일평균 AUTO_SEND 후보가 5건 미만: ⚠️ 데이터 부족, Shadow Mode 유지

### 1.3 SEND_FAILED 비율 확인

```sql
-- 최근 30일간 전송 실패율 (Shadow Mode에서의 실패 기록)
SELECT
    market_code,
    COUNT(*) as total_attempts,
    SUM(CASE WHEN send_status = 'SEND_FAILED' THEN 1 ELSE 0 END) as failed_count,
    SUM(CASE WHEN send_status = 'SEND_FAILED' THEN 1 ELSE 0 END)::float / COUNT(*) * 100 as failure_rate
FROM market_inquiry_raw
WHERE send_attempts > 0
  AND created_at >= NOW() - INTERVAL '30 days'
GROUP BY market_code;
```

**기준:**
- 실패율 0%: ✅ 완벽
- 실패율 < 5%: ✅ 양호
- 실패율 5-10%: ⚠️ 모니터링 필요
- 실패율 > 10%: ❌ 원인 파악 후 해금

---

## 🚀 Phase 2: TEST_MODE 안전장치 활성화

### 2.1 .env 설정

```bash
# .env 파일에 추가
ENABLE_CS_PARTIAL_AUTO=true
CS_TEST_MODE=true
CS_TEST_MODE_ALLOWED_ACCOUNTS=account_id_1,account_id_2
```

**설명:**
- `ENABLE_CS_PARTIAL_AUTO=true`: Partial Auto 스위치 ON
- `CS_TEST_MODE=true`: 실제 마켓 API 전송 차단 (테스트 모드)
- `CS_TEST_MODE_ALLOWED_ACCOUNTS`: 테스트용 계정 ID (선택)

### 2.2 TEST_MODE 동작 확인

```bash
# 로그 확인
tail -f api.log | grep TEST_MODE
```

**기대 로그:**
```
[WARNING] [TEST_MODE] Skipping real API send for inquiry xxx (account yyy not in allowed list)
[INFO] Inquiry xxx locked as SENDING for atomic send
[INFO] Successfully auto-sent inquiry xxx
```

**검증 포인트:**
- 실제 쿠팡/네이버로 전송되지 않음
- DB 상태는 SEND_FAILED로 기록되되, TEST_MODE 마크 있음
- last_send_error에 `[TEST_MODE] Real API send blocked` 포함

---

## 🎯 Phase 3: 계정별 단계적 해금

### 3.1 계정 선정 기준

| 우선순위 | 계정 유형 | 이유 | 권장 AUTO_SEND 대상 |
|---------|---------|------|-------------------|
| 1순위 | 쿠팡(메인) | API 안정성 높음, 자동화 이력 있음 | 배송문의, 사용법 |
| 2순위 | 스마트스토어 | 자동화 도입 단계 | 사용법만 |
| 3순위 | 쿠팡(보조) | 메인 안정화 후 확장 | 배송문의만 |

### 3.2 1단계: 쿠팡 메인 계정 해금

#### 3.2.1 계정 ID 확인

```sql
-- 쿠팡 메인 계정 ID 찾기
SELECT id, name, market_code
FROM market_account
WHERE market_code = 'COUPANG'
  AND is_active = true;
```

**예시 결과:**
```
  id  | name        | market_code
------+-------------+-------------
 uuid1 | coupang_main | COUPANG
 uuid2 | coupang_sub  | COUPANG
```

#### 3.2.2 .env 설정 (쿠팡 메인만 허용)

```bash
# .env
ENABLE_CS_PARTIAL_AUTO=true
CS_TEST_MODE=false  # 실제 전송 허용
CS_TEST_MODE_ALLOWED_ACCOUNTS=uuid1  # 쿠팡 메인만
CS_AUTO_SEND_THRESHOLD=0.90  # 신뢰도 임계값 (기본값)
```

#### 3.2.3 자동화 대상 제한 (의도 필터링)

`app/services/ai/agents/automation_policy.py`에서 제한된 의도만 AUTO_SEND:

```python
# Phase 3.2.3: 1단계에서는 안전한 의도만 허용
ALLOWED_INTENTS_PHASE_1 = ["배송문의", "사용법"]  # 배송문의, 사용법만
ALLOWED_INTENTS_PHASE_2 = ["배송문의", "사용법", "상품문의"]  # 확장 시
ALLOWED_INTENTS_PHASE_3 = None  # 전체 허용
```

**Policy Engine 수정 예시:**

```python
# app/services/ai/agents/automation_policy.py

def evaluate(self, state: CSAgentState) -> tuple[bool, str, dict]:
    intent = state.get("intent", "")

    # Phase 1: 허용된 의도만 AUTO_SEND
    ALLOWED_INTENTS = ["배송문의", "사용법"]
    if intent not in ALLOWED_INTENTS:
        return False, f"Intent '{intent}' not in allowed list (Phase 1)", {"final_score": 0.0}

    # ... 기존 평가 로직 ...
```

#### 3.2.4 일일 쿼터 제한

```sql
-- 일일 전송 제한 확인 (설정 필요 시)
SELECT
    DATE(created_at) as date,
    account_id,
    COUNT(*) as count
FROM market_inquiry_raw
WHERE send_status = 'SENT'
  AND created_at >= NOW() - INTERVAL '1 day'
GROUP BY DATE(created_at), account_id
HAVING COUNT(*) > 10;  # 일일 10건 초과 시 알림
```

**권장 설정:**
- Phase 1: 일일 10건 제한
- Phase 2: 일일 30건 제한
- Phase 3: 제한 없음

---

### 3.3 2단계: 쿠팡 보조 + 스마트스토어 확장

#### 3.3.1 .env 설정

```bash
# .env
ENABLE_CS_PARTIAL_AUTO=true
CS_TEST_MODE=false
CS_TEST_MODE_ALLOWED_ACCOUNTS=uuid1,uuid2,uuid3  # 쿠팡 메인, 보조 + 스마트스토어
CS_AUTO_SEND_THRESHOLD=0.90
```

#### 3.3.2 의도 확장

```python
ALLOWED_INTENTS = ["배송문의", "사용법", "상품문의"]  # 상품문의 추가
```

#### 3.3.3 일일 쿼터 확장

- 일일 30건 제한

---

### 3.4 3단계: 전면 해금

#### 3.4.1 .env 설정

```bash
# .env
ENABLE_CS_PARTIAL_AUTO=true
CS_TEST_MODE=false
CS_TEST_MODE_ALLOWED_ACCOUNTS=  # 빈 값 = 전체 허용
CS_AUTO_SEND_THRESHOLD=0.90
```

#### 3.4.2 의도 제한 해제

```python
ALLOWED_INTENTS = None  # 전체 허용
```

#### 3.4.3 일일 쿼터 해제

---

## 🔍 Phase 4: 모니터링 & 롤백 조건

### 4.1 실시간 모니터링 지표

#### 4.1.1 핵심 KPI

```sql
-- 실시간 AUTO_SEND 현황 (최근 1시간)
SELECT
    market_code,
    COUNT(*) as total,
    SUM(CASE WHEN send_status = 'SENT' THEN 1 ELSE 0 END) as sent,
    SUM(CASE WHEN send_status = 'SEND_FAILED' THEN 1 ELSE 0 END) as failed,
    AVG(confidence_score) as avg_confidence
FROM market_inquiry_raw
WHERE status = 'AUTO_SEND'
  AND created_at >= NOW() - INTERVAL '1 hour'
GROUP BY market_code;
```

#### 4.1.2 롤백 트리거 (v1.8.2 명시)

| 순위 | 조건 | 트리거 | 행동 |
|------|------|--------|------|
| 🚨 즉시 | "법적", "소비자원", "클레임" 키워드 포함 건이 AUTO_SEND로 탐지됨 | 즉시 OFF | `CS_TEST_MODE=true`로 긴급 롤백 |
| 🚨 즉시 | 동일 계정에서 연속 3건 실패 | 즉시 OFF | 해당 계정 해금 해제 |
| 🚨 즉시 | 1시간 내 SEND_FAILED > 5건 | 즉시 OFF | `CS_TEST_MODE=true`로 긴급 롤백 |
| ⚠️ 24시간 | 24시간 내 실패율 >= 2% | 계정별 롤백 | 문제 계정만 해금 해제 |
| ⚠️ 24시간 | 24시간 내 실패율 >= 5% | 전체 롤백 | `CS_TEST_MODE=true`로 전체 차단 |
| ⚠️ 7일 | 7일 연속 실패율 >= 3% | Shadow Mode로 복귀 | `ENABLE_CS_PARTIAL_AUTO=false` |

### 4.2 롤백 절차

#### 4.2.1 긴급 롤백 (즉시)

```bash
# .env 수정
CS_TEST_MODE=true  # 모든 전송 차단
```

#### 4.2.2 계정별 롤백

```bash
# .env 수정
CS_TEST_MODE_ALLOWED_ACCOUNTS=uuid1  # 문제 계정만 제외
```

#### 4.2.3 롤백 후 확인

```sql
-- 롤백 후 추가 실패 없는지 확인
SELECT *
FROM market_inquiry_raw
WHERE send_status = 'SEND_FAILED'
  AND created_at >= NOW() - INTERVAL '10 minutes'
ORDER BY created_at DESC;
```

---

## ✅ Phase 5: 안정화 후 프로덕션 전환

### 5.1 7일 모니터링 결과 기준

| 지표 | 기준 | Phase 1 | Phase 2 | Phase 3 |
|------|------|---------|---------|---------|
| 일평균 AUTO_SEND 건수 | 10+ | ✅ | ✅ | ✅ |
| 실패율 (24시간) | < 5% | ✅ | ✅ | ✅ |
| 고객 불만족 레포트 | 0건 | ✅ | ✅ | ✅ |

### 5.2 최종 승인 체크리스트

- [ ] 모든 Production-Ready 테스트 통과
- [ ] Phase 1-4 모두 완료
- [ ] 7일 연속 실패율 < 5%
- [ ] 운영팀 교육 완료
- [ ] 롤백 절차 문서 공유
- [ ] 모니터링 대시보드 설정 완료

---

## 📞 운영팀 연락처 (긴급시)

- **개발팀**: [팀원 이름]
- **DBA**: [팀원 이름]
- **CS팀 리드**: [팀원 이름]

---

## 📚 관련 문서

- Production-Ready 패치: `tests/test_partial_auto_production_ready.py`
- CS Workflow Agent: `app/services/ai/agents/cs_workflow_agent.py`
- Automation Policy: `app/services/ai/agents/automation_policy.py`
- 설정: `app/settings.py`

---

## 📝 변경 이력

| 날짜 | 버전 | 변경 내용 | 작성자 |
|------|------|---------|--------|
| 2025-12-31 | v1.8.1 | Production-Ready 패치 + 단계적 해금 가이드 | AI Agent |
