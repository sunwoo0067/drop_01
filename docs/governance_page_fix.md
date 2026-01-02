# 프론트엔드 빌드 오류 해결 - 기본 HTML 구현

## 📋 오류 원인 분석

### 발생한 빌드 오류
```
Export Input doesn't exist in target module
./src/app/dashboard/LogViewer.tsx:4:1
import { Search, Download, X, Activity, RefreshCw } from "lucide-react";
```

### 🎯 핵심 원인
1. **설치되지 않은 외부 라이브러리**: `lucide-react`가 설치되어 있지 않거나 경로가 올바르지 않음
2. **불필요한 import**: 프로젝트는 기본 HTML 엘리먼트와 Tailwind CSS만 사용

---

## ✅ 해결 방안: 기본 HTML로 구현

### 작업 대상
**파일**: `frontend/src/app/governance/page.tsx`

### 수정 전략
1. **모든 외부 UI 컴포넌트 import 제거**
   ```tsx
   // 제거할 import들
   // import { Search, Download, X, Activity, RefreshCw } from "lucide-react";
   // import { Input } from "@/components/ui/Input";
   // import { Select } from "@/components/ui/Select";
   // import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
   ```

2. **기본 React Hooks와 Tailwind CSS만 사용**
   ```tsx
   'use client';
   import { useState, useEffect } from 'react';
   ```

3. **인라인 스타일 적용 (className 속성)**

### 수정된 코드 구조

#### 1. 기본 설정
```tsx
'use client';

import { useState, useEffect } from 'react';

export default function GovernancePage() {
  const [policies, setPolicies] = useState<any[]>([]);
  const [decisionLogs, setDecisionLogs] = useState<any[]>([]);
  const [segmentStats, setSegmentStats] = useState<any[]>([]);
  const [globalKillSwitch, setGlobalKillSwitch] = useState(false);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [policiesRes, logsRes, statsRes, killSwitchRes] = await Promise.all([
        fetch('/api/autonomy/policies?limit=100'),
        fetch('/api/autonomy/decision-logs?limit=100'),
        fetch('/api/autonomy/segment-stats?days=7'),
        fetch('/api/autonomy/kill-switch/processing'),
      ]);

      const policiesData = await policiesRes.json();
      const logsData = await logsRes.json();
      const statsData = await statsRes.json();
      const killSwitchData = await killSwitchRes.json();

      setPolicies(policiesData);
      setDecisionLogs(logsData);
      setSegmentStats(statsData);
      setGlobalKillSwitch(killSwitchData.enabled);
    } catch (error) {
      console.error('데이터 가져오기 실패:', error);
    } finally {
      setLoading(false);
    }
  };
```

#### 2. 기본 HTML 테이블 스타일
```tsx
  // 테이블 스타일
  const tableStyles = "min-w-full bg-white border";
  const headerStyles = "px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-700";
  const cellStyles = "px-4 py-3 text-sm";
```

---

## 📝 수정된 파일 전체 내용

이 수정을 적용하여 빌드 오류를 해결하고, 기본 HTML 엘리먼트로 대시보드를 구현합니다.

### 주요 변경 사항
1. `lucide-react` 등 불필요 import 모두 제거
2. 기본 React Hooks(`useState`, `useEffect`)만 사용
3. Tailwind CSS 인라인 스타일(className) 적용
4. 불필요한 컴포넌트 레퍼런스 참조 제거

---

## 🎯 예상 결과

### 빌드 성공
```bash
cd frontend
npm run build
```
빌드가 성공적으로 완료되어야 합니다.

### 대시보드 실행
```bash
cd frontend
npm run start
```

대시보드가 `http://localhost:3333/governance`에서 실행되어야 합니다.

---

**참고**: 이 수정으로 인라인 스타일만 사용하므로 디자인 테일 사용 가능합니다. 차후에 Shadcn UI 컴포넌트가 설치되면 이 코드와 호환됩니다.
