/**
 * 자율성 거버넌스 대시보드
 * 
 * 이 페이지는 다음 기능을 제공합니다:
 * 1. 세그먼트별 자율 등급(Tier) 시각화
 * 2. 전환 히스토리 (승격/강등 이력)
 * 3. 성공률 및 신뢰도 지표
 * 4. 의사결정 로그 뷰어
 * 5. 전역 킬스위치
 */
'use client';

import { useState, useEffect } from 'react';

// NOTE: UI 컴포넌트(lucide-react 등)는 현재 설치되어 있지 않으므로,
// 기본 HTML/Tailwind CSS를 사용하여 UI를 구현합니다.

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
      // 실제 API 호출
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

  const handleGlobalKillSwitch = async (enabled: boolean) => {
    try {
      const res = await fetch('/api/autonomy/kill-switch/processing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });

      if (!res.ok) {
        throw new Error('전역 킬스위치 설정 실패');
      }

      setGlobalKillSwitch(enabled);
      if (enabled) {
        alert('⚠️ 전역 킬스위치가 활성화되었습니다. 모든 자율 동작이 중단됩니다.');
      } else {
        alert('✅ 전역 킬스위치가 비활성화되었습니다. 자율 동작이 재개됩니다.');
      }
    } catch (error) {
      console.error('전역 킬스위치 설정 실패:', error);
      alert('전역 킬스위치 설정에 실패했습니다.');
    }
  };

  const getTierBadge = (tier: number) => {
    const colors: { [key: number]: string } = {
      0: 'bg-gray-500',
      1: 'bg-blue-500',
      2: 'bg-green-500',
      3: 'bg-purple-500',
    };
    const labels: { [key: number]: string } = {
      0: 'Tier 0 (수동)',
      1: 'Tier 1 (Enforce Lite)',
      2: 'Tier 2 (High-Confidence)',
      3: 'Tier 3 (Full Auto)',
    };
    return (
      <span className={`px-2 py-1 rounded-full text-white text-sm font-medium ${colors[tier]}`}>
        {labels[tier]}
      </span>
    );
  };

  const getDecisionBadge = (decision: string) => {
    const colors: { [key: string]: string } = {
      APPLIED: 'bg-green-500',
      PENDING: 'bg-yellow-500',
      REJECTED: 'bg-red-500',
    };
    const labels: { [key: string]: string } = {
      APPLIED: '적용',
      PENDING: '대기',
      REJECTED: '거절',
    };
    return (
      <span className={`px-2 py-1 rounded-full text-white text-sm font-medium ${colors[decision]}`}>
        {labels[decision]}
      </span>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-lg">로딩 중...</div>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8 px-4">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">자율성 거버넌스 대시보드</h1>
        <p className="text-gray-600">
          AI 자율 의사결정 시스템의 현황을 모니터링하고 제어합니다.
        </p>
      </div>

      {/* 전역 킬스위치 */}
      <div className="mb-8 p-6 bg-white border border-red-200 rounded-lg shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-red-600 mb-2">⚠️ 전역 킬스위치</h2>
            <p className="text-gray-600">
              긴급 상황 시 즉시 모든 자율 동작을 멈춥니다.
            </p>
          </div>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={globalKillSwitch}
              onChange={(e) => handleGlobalKillSwitch(e.target.checked)}
              className="w-6 h-6 text-red-600 rounded focus:ring-red-500"
            />
            <span className="text-lg font-medium">
              {globalKillSwitch ? '활성화 (모든 자율 동작 중단)' : '비활성화 (자율 동작 정상)'}
            </span>
          </label>
        </div>
        {globalKillSwitch && (
          <div className="mt-4 p-4 bg-red-50 border border-red-500 rounded-lg">
            <p className="font-bold text-red-800">⚠️ 경고</p>
            <p className="text-red-700 text-sm mt-1">
              전역 킬스위치가 활성화되어 있습니다. 모든 가격 변경 및 상품 가공의
              자동 실행이 중단됩니다.
            </p>
          </div>
        )}
      </div>

      {/* 탭 네비게이션 */}
      <div className="mb-4 flex gap-2 border-b">
        <button
          onClick={() => setActiveTab('overview')}
          className={`px-4 py-2 font-medium ${
            activeTab === 'overview' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-600'
          }`}
        >
          개요
        </button>
        <button
          onClick={() => setActiveTab('policies')}
          className={`px-4 py-2 font-medium ${
            activeTab === 'policies' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-600'
          }`}
        >
          정책 관리
        </button>
        <button
          onClick={() => setActiveTab('decisions')}
          className={`px-4 py-2 font-medium ${
            activeTab === 'decisions' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-600'
          }`}
        >
          의사결정 로그
        </button>
        <button
          onClick={() => setActiveTab('stats')}
          className={`px-4 py-2 font-medium ${
            activeTab === 'stats' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-600'
          }`}
        >
          성과 분석
        </button>
      </div>

      {/* 개요 탭 */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <div className="p-6 bg-white border rounded-lg shadow-sm">
            <h3 className="text-lg font-semibold mb-2">총 정책 수</h3>
            <div className="text-4xl font-bold">{policies.length}</div>
          </div>
          <div className="p-6 bg-white border rounded-lg shadow-sm">
            <h3 className="text-lg font-semibold mb-2">활성 정책</h3>
            <div className="text-4xl font-bold text-green-600">
              {policies.filter((p: any) => p.status === 'ACTIVE').length}
            </div>
          </div>
          <div className="p-6 bg-white border rounded-lg shadow-sm">
            <h3 className="text-lg font-semibold mb-2">총 의사결정</h3>
            <div className="text-4xl font-bold">{decisionLogs.length}</div>
          </div>
          <div className="p-6 bg-white border rounded-lg shadow-sm">
            <h3 className="text-lg font-semibold mb-2">자동 승인율</h3>
            <div className="text-4xl font-bold text-blue-600">
              {decisionLogs.length > 0
                ? ((decisionLogs.filter((l: any) => l.decision === 'APPLIED').length / decisionLogs.length) * 100).toFixed(1)
                : '0.0'}%
            </div>
          </div>
        </div>
      )}

      {/* 정책 관리 탭 */}
      {activeTab === 'policies' && (
        <div className="p-6 bg-white border rounded-lg shadow-sm">
          <h2 className="text-xl font-bold mb-4">세그먼트별 자율성 정책</h2>
          <p className="text-gray-600 mb-4">각 세그먼트별 자율 등급(Tier)을 관리합니다.</p>
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="border-b">
                  <th className="px-4 py-3 text-left">세그먼트</th>
                  <th className="px-4 py-3 text-left">벤더</th>
                  <th className="px-4 py-3 text-left">채널</th>
                  <th className="px-4 py-3 text-left">카테고리</th>
                  <th className="px-4 py-3 text-left">자율 등급</th>
                  <th className="px-4 py-3 text-left">상태</th>
                  <th className="px-4 py-3 text-left">최종 업데이트</th>
                </tr>
              </thead>
              <tbody>
                {policies.map((policy) => (
                  <tr key={policy.id} className="border-b hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-xs max-w-xs truncate">
                      {policy.segment_key}
                    </td>
                    <td className="px-4 py-3">{policy.vendor || '-'}</td>
                    <td className="px-4 py-3">{policy.channel || '-'}</td>
                    <td className="px-4 py-3">{policy.category_code || '-'}</td>
                    <td className="px-4 py-3">{getTierBadge(policy.tier)}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-sm font-medium ${
                        policy.status === 'ACTIVE' ? 'bg-blue-500 text-white' : 'bg-gray-500 text-white'
                      }`}>
                        {policy.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {new Date(policy.updated_at).toLocaleDateString('ko-KR')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 의사결정 로그 탭 */}
      {activeTab === 'decisions' && (
        <div className="p-6 bg-white border rounded-lg shadow-sm">
          <h2 className="text-xl font-bold mb-4">자율적 의사결정 이력</h2>
          <p className="text-gray-600 mb-4">
            AI가 어떤 근거로 가격/가공을 승인/반려했는지 확인합니다.
          </p>
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="border-b">
                  <th className="px-4 py-3 text-left">시간</th>
                  <th className="px-4 py-3 text-left">세그먼트</th>
                  <th className="px-4 py-3 text-left">티어</th>
                  <th className="px-4 py-3 text-left">결정</th>
                  <th className="px-4 py-3 text-left">신뢰도</th>
                  <th className="px-4 py-3 text-left">마진</th>
                  <th className="px-4 py-3 text-left">사유</th>
                </tr>
              </thead>
              <tbody>
                {decisionLogs.map((log) => (
                  <tr key={log.id} className="border-b hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm">
                      {new Date(log.created_at).toLocaleString('ko-KR')}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs max-w-xs truncate">
                      {log.segment_key}
                    </td>
                    <td className="px-4 py-3">Tier {log.tier_used}</td>
                    <td className="px-4 py-3">{getDecisionBadge(log.decision)}</td>
                    <td className="px-4 py-3">
                      {log.confidence !== undefined ? `${(log.confidence * 100).toFixed(1)}%` : '-'}
                    </td>
                    <td className="px-4 py-3">
                      {log.expected_margin !== undefined ? `${(log.expected_margin * 100).toFixed(1)}%` : '-'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-xs space-y-1">
                        {log.reasons.map((reason, idx) => (
                          <div key={idx}>{reason}</div>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 성과 분석 탭 */}
      {activeTab === 'stats' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="p-6 bg-white border rounded-lg shadow-sm">
            <h2 className="text-xl font-bold mb-4">세그먼트별 성과</h2>
            <p className="text-gray-600 mb-4">세그먼트별 성공률 및 신뢰도 지표</p>
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead>
                  <tr className="border-b">
                    <th className="px-4 py-3 text-left">세그먼트</th>
                    <th className="px-4 py-3 text-left">티어</th>
                    <th className="px-4 py-3 text-left">총 결정</th>
                    <th className="px-4 py-3 text-left">성공률</th>
                    <th className="px-4 py-3 text-left">평균 신뢰도</th>
                  </tr>
                </thead>
                <tbody>
                  {segmentStats.map((stat) => (
                    <tr key={stat.segment_key} className="border-b hover:bg-gray-50">
                      <td className="px-4 py-3">{stat.segment_key}</td>
                      <td className="px-4 py-3">Tier {stat.tier}</td>
                      <td className="px-4 py-3">{stat.total_decisions}</td>
                      <td className="px-4 py-3">
                        <span className={
                          stat.success_rate >= 0.9 ? 'text-green-600' :
                          stat.success_rate >= 0.8 ? 'text-yellow-600' : 'text-red-600'
                        }>
                          {(stat.success_rate * 100).toFixed(1)}%
                        </span>
                      </td>
                      <td className="px-4 py-3">{(stat.avg_confidence * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="p-6 bg-white border rounded-lg shadow-sm">
            <h2 className="text-xl font-bold mb-4">승격/강등 가이드라인</h2>
            <p className="text-gray-600 mb-4">자율 등급 전환 기준</p>
            <div className="space-y-4">
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                <h4 className="font-bold text-green-800 mb-2">✅ 승격 기준 (Tier 증가)</h4>
                <ul className="text-sm space-y-1 text-green-700">
                  <li>• 14일 간 안정 성공률 90% 이상</li>
                  <li>• 평균 신뢰도 0.96 이상</li>
                  <li>• 최소 30건 이상의 결정 이력</li>
                </ul>
              </div>
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                <h4 className="font-bold text-red-800 mb-2">⚠️ 강등 기준 (Tier 감소)</h4>
                <ul className="text-sm space-y-1 text-red-700">
                  <li>• 최근 24시간 내 반려율 50% 초과</li>
                  <li>• 최소 10건 이상의 결정 이력</li>
                  <li>• 강등 시 Tier 0으로 즉시 동결</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
