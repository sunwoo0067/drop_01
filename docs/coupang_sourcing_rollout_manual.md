# 쿠팡 소싱 정책 엔진 운영 매뉴얼 (Rollout Manual)

본 문서는 Coupang Sourcing Policy Engine(Option C)의 운영 관리와 단계별 롤아웃을 위한 최종 가이드를 담고 있습니다.

## 1. 운영 핵심 지표 (KPI Checklist)

시스템이 기대대로 작동하는지 판단하기 위해 `GET /analytics/coupang/operational-stats` API를 통해 다음 지표를 매일 관측합니다.

| 지표명 | 정상 범위 (신호등) | 대응 액션 |
| :--- | :--- | :--- |
| **등급 분포 (CORE + TRY)** | **40% 이상** | 정책 엔진의 리스크 필터링이 건강함 |
| **BLOCK 비율** | **60% 미만** | 60% 이상 시 키워드/카테고리 매핑 로직 점검 필요 |
| **문서/인증 스킵률** | **하향 추세 유지** | 정책 엔진이 저품질 카테고리를 잘 걸러내고 있음 |
| **Fallback 의존도** | **50% 이하 유지** | 정확 매칭 비율이 높을수록 안정적 |

## 2. 단계별 운영 전환 가이드

### Phase 0: Shadow Mode (현재)
- **목적**: 실제 차단 없이 데이터 수집 및 정책 시뮬레이션.
- **설정**: `COUPANG_SOURCING_POLICY_MODE=shadow`
- **전환 트리거**: 아래 조건 충족 시 다음 단계로 이동.
    1. Shadow 모드 운영 24~48시간 경과.
    2. 쿠팡 등록 성공률 유지 또는 상승 확인.
    3. CORE/TRY 상품 공급량이 일일 소싱 목표치 충족.

### Phase 1: Enforce-Lite (안정화)
- **목적**: BLOCK 등급 상품 차단 및 신규 키워드(RESEARCH) 제한적 허용.
- **설정**: `COUPANG_SOURCING_POLICY_MODE=enforce_lite`
- **특징**: 리스크 있는 카테고리는 걸러내면서 안전하게 자동화 효율을 높이는 단계.

### Phase 2: Full Enforce (최적화)
- **목적**: 정책 엔진의 모든 액션을 실 적용하여 자원 배분 최적화.
- **설정**: `COUPANG_SOURCING_POLICY_MODE=enforce`

## 3. 리스크 대응 (Rollback & Switches)

- **자동 가드레일**: 성공률 30%p 급락 시 시스템이 자동으로 `enforce_lite` 또는 `stability_mode` 진입을 제안합니다.
- **수동 복귀**: 이슈 발생 시 즉시 환경변수를 `shadow`로 변경하여 소싱 차단을 해제할 수 있습니다.
- **Stability Mode**: `COUPANG_STABILITY_MODE=true` 설정 시 모든 Fallback 로직을 중단하고 안전한 확정 카테고리만 사용합니다.

---
**"이 시스템은 학습 결과로 소싱을 통제하는 '데이터 기반 운영 엔진'입니다."**
운영 중 수치가 임계치를 벗어날 경우, 엔진 튜닝 또는 카테고리 가중치 조정을 통해 대응하십시오.
