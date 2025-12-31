# Shadow Mode KPI Metrics & SQL Template 📊

Shadow Mode 운영 기간 동안 수집된 데이터를 바탕으로 자동화의 안전성을 정량적으로 증명하기 위한 지표 정의서입니다.

## 1. 핵심 모니터링 지표 (KPIs)

| 지표명 | 추출 위치 | 비즈니스 의미 | 목표 (Target) |
| :--- | :--- | :--- | :--- |
| **Confidence Distribution** | `market_inquiry_raw.confidence_score` | AI 모델의 전반적인 확신 단계 파악 | 0.90 이상이 전체의 60% 이상 |
| **Shadow-to-Auto Conversion Rate** | `status` == 'AI_DRAFTED' 비율 | 현재 정책 기준 자동화 가능 범위 | 40% ~ 50% 시작 권장 |
| **Penalty Hit Rate** | `cs_metadata.intent_penalty` != 0 | 리스크 엔진이 고위험군을 얼마나 걸러내는지 | - |
| **Security Filter Rate** | `cs_metadata.security_filters` 감지 수 | 보안 위협(법적/클레임) 발생 빈도 | - |

---

## 2. 분석용 SQL 템플릿 (PostgreSQL)

### A. 일일 운영 상태 요약
```sql
SELECT 
    DATE(fetched_at) as date,
    status,
    send_status, -- v1.8.0 추가
    COUNT(*) as count,
    ROUND(AVG(confidence_score)::numeric, 3) as avg_confidence
FROM market_inquiry_raw
WHERE fetched_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY 1, 2, 3
ORDER BY 1 DESC, 2;
```

### B. "만약 자동화였다면?" (Partial Auto 시뮬레이션)
정책 엔진의 리스크 페널티가 적용된 후에도 생존한 건들을 조회합니다.
```sql
SELECT 
    inquiry_id,
    market_code,
    confidence_score as raw_score,
    (cs_metadata->'policy_evaluation'->>'final_score')::float as final_score,
    cs_metadata->'policy_evaluation'->>'intent' as intent,
    ai_suggested_answer
FROM market_inquiry_raw
WHERE (cs_metadata->'policy_evaluation'->>'final_score')::float >= 0.90
  AND status IN ('AI_DRAFTED', 'AUTO_SEND')
ORDER BY (cs_metadata->'policy_evaluation'->>'final_score')::float DESC;
```

### C. 주요 리스크 페널티 발생 원인 TOP 5
```sql
SELECT 
    cs_metadata->'policy_evaluation'->>'intent' as intent,
    cs_metadata->'policy_evaluation'->>'blocked_reason' as reason,
    COUNT(*) as cases
FROM market_inquiry_raw
WHERE (cs_metadata->'policy_evaluation'->'intent_penalty')::float > 0
GROUP BY 1, 2
ORDER BY 3 DESC;
```

### D. [v1.8.0] 전송 성공/실패 모니터링
```sql
SELECT 
    market_code,
    send_status,
    COUNT(*) as count,
    ROUND(AVG(send_attempts), 1) as avg_attempts,
    MAX(last_send_error) as sample_error
FROM market_inquiry_raw
WHERE status = 'AUTO_SEND'
GROUP BY 1, 2;
```

---

## 3. v1.8.0 진입 의사결정 기준 (Gate)
- **정량 기준**: `final_score` >= 0.90 인 건수가 일평균 10건 이상 & 7일간 유지
- **정성 기준**: `AI_DRAFTED` 상태인 답변 50개를 랜덤 샘플링하여 운영자가 검토했을 때 "전송 가능" 의견이 95% 이상
