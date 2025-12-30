"use client";

import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Table, TableColumn } from "@/components/ui/Table";
import { DashboardToolbar } from "./dashboard/DashboardToolbar";
import { OverallStats, StatTable } from "./dashboard/StatTable";
import { OrchestrationControl } from "./dashboard/OrchestrationControl";
import { LogViewer } from "./dashboard/LogViewer";
import { ShieldCheck, CheckCircle, AlertTriangle, RotateCcw, FileText } from "lucide-react";

type LogFilter = {
  step: string;
  status: string;
  search: string;
};

export default function Home() {
  const [stats, setStats] = useState({
    total: 0,
    pending: 0,
    completed: 0
  });
  const [dashboardStats, setDashboardStats] = useState<any>(null);
  const [activeTab, setActiveTab] = useState("overall");
  const [events, setEvents] = useState<any[]>([]);
  const [filteredEvents, setFilteredEvents] = useState<any[]>([]);
  const [marketStats, setMarketStats] = useState<any[]>([]);
  const [gatingReport, setGatingReport] = useState<any | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // 로그 필터 상태
  const [logFilter, setLogFilter] = useState<LogFilter>({
    step: "ALL",
    status: "ALL",
    search: ""
  });

  // 설정 패널 상태
  const [showSettings, setShowSettings] = useState(false);
  const [settings, setSettings] = useState({
    listing_limit: 15000,
    sourcing_keyword_limit: 30,
    continuous_mode: false
  });

  // 오케스트레이션 진행률
  const [orchestrationProgress, setOrchestrationProgress] = useState({
    currentStep: "",
    progress: 0,
    totalSteps: 0
  });

  // 알림 상태
  const [notifications, setNotifications] = useState<any[]>([]);
  const [showNotifications, setShowNotifications] = useState(false);

  const fetchStats = useCallback(async () => {
    try {
      const res = await api.get("/products/stats");
      setStats(res.data);
      const dashboardRes = await api.get("/analytics/dashboard/stats");
      setDashboardStats(dashboardRes.data);
    } catch (e) {
      console.error("Failed to fetch stats", e);
      setStats({ total: 0, pending: 0, completed: 0 });
    }
  }, []);

  const addNotification = useCallback((notification: any) => {
    setNotifications(prev => [notification, ...prev].slice(0, 10));
  }, []);

  const updateOrchestrationProgress = useCallback((latestEvent: any) => {
    const steps = ["PLANNING", "OPTIMIZATION", "SOURCING", "LISTING", "PREMIUM", "COMPLETE"];
    const currentIndex = steps.indexOf(latestEvent.step);
    setOrchestrationProgress({
      currentStep: latestEvent.step,
      progress: currentIndex >= 0 ? (currentIndex / (steps.length - 1)) * 100 : 0,
      totalSteps: steps.length
    });
  }, []);

  const fetchEvents = useCallback(async () => {
    try {
      const res = await api.get("/orchestration/events?limit=50");
      setEvents(res.data);
      setLastUpdatedAt(new Date());

      if (res.data.length > 0) {
        const latest = res.data[0];
        if (latest.status === "START" || latest.status === "IN_PROGRESS") {
          setIsRunning(true);
          updateOrchestrationProgress(latest);
        } else if (latest.step === "COMPLETE" || latest.status === "SUCCESS") {
          setIsRunning(false);
          setOrchestrationProgress({ currentStep: "", progress: 0, totalSteps: 0 });
        }

        if (latest.status === "FAIL") {
          addNotification({
            type: "error",
            title: "오케스트레이션 실패",
            message: latest.message || "알 수 없는 오류가 발생했습니다.",
            time: new Date()
          });
        }
      }
    } catch (e) {
      console.error("Failed to fetch events", e);
    }
  }, [addNotification, updateOrchestrationProgress]);

  const fetchMarketStats = useCallback(async () => {
    try {
      const res = await api.get("/market/stats");
      setMarketStats(res.data);
    } catch (e) {
      console.error("Failed to fetch market stats", e);
    }
  }, []);

  const fetchGatingReport = useCallback(async () => {
    try {
      const res = await api.get("/orchestration/coupang-gating?limit=20&days=7");
      setGatingReport(res.data);
    } catch (e) {
      console.error("Failed to fetch coupang gating report", e);
    }
  }, []);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await api.get("/settings/orchestrator");
      setSettings(prev => res.data || prev);
    } catch (e) {
      console.error("Failed to fetch settings", e);
    }
  }, []);

  const updateSettings = async () => {
    try {
      await api.post("/settings/orchestrator", settings);
      alert("설정이 저장되었습니다.");
      setShowSettings(false);
    } catch (e) {
      console.error("Failed to update settings", e);
      alert("설정 저장에 실패했습니다.");
    }
  };

  // 로그 필터링
  useEffect(() => {
    let filtered = [...events];

    if (logFilter.step !== "ALL") {
      filtered = filtered.filter(e => e.step === logFilter.step);
    }

    if (logFilter.status !== "ALL") {
      filtered = filtered.filter(e => e.status === logFilter.status);
    }

    if (logFilter.search) {
      const searchLower = logFilter.search.toLowerCase();
      filtered = filtered.filter(e =>
        e.message?.toLowerCase().includes(searchLower) ||
        e.step?.toLowerCase().includes(searchLower)
      );
    }

    setFilteredEvents(filtered);
  }, [events, logFilter]);

  useEffect(() => {
    fetchStats();
    fetchEvents();
    fetchMarketStats();
    fetchGatingReport();
    fetchSettings();

    const interval = setInterval(() => {
      fetchStats();
      fetchEvents();
      fetchMarketStats();
      fetchGatingReport();
    }, 5000);

    return () => clearInterval(interval);
  }, [fetchEvents, fetchMarketStats, fetchGatingReport, fetchSettings, fetchStats]);

  const handleRunCycle = async (dryRun: boolean = true) => {
    console.log(`Triggering orchestration cycle: dryRun=${dryRun}`);
    setIsLoading(true);
    try {
      await api.post(`/orchestration/run-cycle?dryRun=${dryRun}`);
      setIsRunning(true);
      addNotification({
        type: "info",
        title: dryRun ? "테스트 가동 시작" : "자동 운영 시작",
        message: dryRun ? "테스트 가동이 시작되었습니다." : "AI 자율 운영이 시작되었습니다.",
        time: new Date()
      });
    } catch (e) {
      console.error("Failed to run cycle", e);
      addNotification({
        type: "error",
        title: "가동 실패",
        message: "AI 가동 요청에 실패했습니다.",
        time: new Date()
      });
    } finally {
      setIsLoading(false);
    }
  };

  const clearNotifications = () => {
    setNotifications([]);
  };

  // 진행률 계산
  const p = dashboardStats?.products || {};
  const totalCompleted = p.refinement_completed || stats.completed || 0;
  const gatingSummary = gatingReport?.summary || {};
  const gatingStats = [
    {
      label: "서류 보류 상품",
      value: gatingSummary.docPendingCount || 0,
      icon: <FileText className="h-3 w-3 text-warning" />,
      description: "서류 대기 상태로 쿠팡 등록이 보류된 상품",
    },
    {
      label: "재시도 큐",
      value: gatingSummary.retryCount || 0,
      icon: <RotateCcw className="h-3 w-3 text-info" />,
      description: "가격/옵션 등 오류로 재시도 대기 중인 상품",
    },
    {
      label: "최근 스킵 로그",
      value: gatingSummary.skipLogCount || 0,
      icon: <AlertTriangle className="h-3 w-3 text-destructive" />,
      description: "최근 7일 내 쿠팡 스킵 로그 건수",
    },
  ];

  return (
    <div className="space-y-3">
      {/* 툴바 */}
      <DashboardToolbar
        isLoading={isLoading}
        isRunning={isRunning}
        onRunCycle={() => handleRunCycle(true)}
        onToggleSettings={() => setShowSettings(!showSettings)}
        onToggleNotifications={() => setShowNotifications(!showNotifications)}
        notificationCount={notifications.length}
      />

      {/* 설정 패널 */}
      {showSettings && (
        <Card className="border border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs">오케스트레이션 설정</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 grid-cols-3">
              <div className="space-y-1.5">
                <label className="text-[10px] font-medium text-muted-foreground">일일 등록 한도</label>
                <Input
                  type="number"
                  value={settings.listing_limit}
                  onChange={(e) => setSettings({ ...settings, listing_limit: parseInt(e.target.value) || 0 })}
                  size="sm"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-[10px] font-medium text-muted-foreground">키워드 소싱 한도</label>
                <Input
                  type="number"
                  value={settings.sourcing_keyword_limit}
                  onChange={(e) => setSettings({ ...settings, sourcing_keyword_limit: parseInt(e.target.value) || 0 })}
                  size="sm"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-[10px] font-medium text-muted-foreground">지속 모드</label>
                <Select
                  value={settings.continuous_mode ? "true" : "false"}
                  onChange={(e) => setSettings({ ...settings, continuous_mode: e.target.value === "true" })}
                  options={[
                    { value: "true", label: "활성화" },
                    { value: "false", label: "비활성화" }
                  ]}
                  className="text-xs h-7"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-border/50">
              <Button variant="outline" size="sm" onClick={() => setShowSettings(false)}>
                취소
              </Button>
              <Button size="sm" onClick={updateSettings}>
                저장
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 알림 패널 */}
      {showNotifications && (
        <Card className="border border-border">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs">시스템 알림</CardTitle>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="xs" onClick={clearNotifications}>
                모두 지우기
              </Button>
              <Button variant="ghost" size="xs" onClick={() => setShowNotifications(false)}>
                닫기
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {notifications.length > 0 ? (
              notifications.map((note, index) => (
                <div
                  key={`${note.title}-${index}`}
                  className="flex items-start justify-between gap-3 rounded-sm border border-border/50 bg-background px-2 py-2"
                >
                  <div className="space-y-0.5 flex-1">
                    <div className="flex items-center gap-2 text-[11px] font-semibold">
                      <span
                        className={
                          note.type === "error"
                            ? "text-destructive"
                            : note.type === "info"
                              ? "text-primary"
                              : "text-foreground"
                        }
                      >
                        {note.title}
                      </span>
                      {note.time && (
                        <span className="text-[9px] text-muted-foreground">
                          {new Date(note.time).toLocaleTimeString()}
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-muted-foreground">{note.message}</p>
                  </div>
                  <span className="text-[9px] font-bold uppercase text-muted-foreground">
                    {note.type}
                  </span>
                </div>
              ))
            ) : (
              <div className="text-center text-xs text-muted-foreground py-6">
                새로운 알림이 없습니다.
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* 탭/필터 바 */}
      <div className="space-y-3">
        <div className="flex items-center justify-between px-3 py-2 border border-border bg-card rounded-sm">
          <div className="flex gap-2 text-[11px]">
            <Button
              variant={activeTab === "overall" ? "primary" : "ghost"}
              size="xs"
              onClick={() => setActiveTab("overall")}
            >
              종합 현황
            </Button>
            <Button
              variant={activeTab === "product" ? "primary" : "ghost"}
              size="xs"
              onClick={() => setActiveTab("product")}
              className="relative"
            >
              상품 현황
              {totalCompleted > 0 && (
                <span className="absolute -top-1 -right-1 h-3 w-3 rounded bg-destructive text-[8px] flex items-center justify-center">
                  {totalCompleted}
                </span>
              )}
            </Button>
            <Button
              variant={activeTab === "market" ? "primary" : "ghost"}
              size="xs"
              onClick={() => setActiveTab("market")}
            >
              마켓 현황 ({marketStats.length})
            </Button>
            <Button
              variant={activeTab === "order" ? "primary" : "ghost"}
              size="xs"
              onClick={() => setActiveTab("order")}
            >
              주문 현황
            </Button>
          </div>
          <div className="text-[9px] text-muted-foreground bg-muted px-2 py-1 rounded-sm">
            마지막 업데이트: {lastUpdatedAt?.toLocaleTimeString()}
          </div>
        </div>

        {/* 종합 현황 */}
        {activeTab === "overall" && (
          <div className="space-y-3">
            <OverallStats stats={stats} dashboardStats={dashboardStats} />
            <OrchestrationControl
              isRunning={isRunning}
              isLoading={isLoading}
              orchestrationProgress={orchestrationProgress}
              onRunCycle={handleRunCycle}
            />
            <div className="grid gap-3 md:grid-cols-[1.1fr,0.9fr]">
              <StatTable title="쿠팡 분기 현황" data={gatingStats} />
              <Card className="border border-border">
                <CardHeader className="py-2">
                  <CardTitle className="text-xs">스킵 원인 TOP</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {(gatingSummary.skipReasonsTop || []).length > 0 ? (
                    (gatingSummary.skipReasonsTop || []).map((row: any, index: number) => (
                      <div
                        key={`reason-${index}`}
                        className="flex items-start justify-between gap-3 rounded-sm border border-border/50 bg-background px-2 py-1.5"
                      >
                        <span className="text-[10px] text-muted-foreground leading-tight">
                          {row[1]}건
                        </span>
                        <span className="text-[10px] text-foreground leading-tight flex-1 text-right">
                          {row[0]}
                        </span>
                      </div>
                    ))
                  ) : (
                    <div className="text-center text-[11px] text-muted-foreground py-4">
                      스킵 로그가 없습니다.
                    </div>
                  )}
                  {gatingSummary.cutoff && (
                    <div className="text-[9px] text-muted-foreground text-right">
                      기준 시각: {new Date(gatingSummary.cutoff).toLocaleString()}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
            <LogViewer
              filteredEvents={filteredEvents}
              logFilter={logFilter}
              setLogFilter={setLogFilter}
              autoScroll={autoScroll}
              setAutoScroll={setAutoScroll}
            />
          </div>
        )}

        {/* 상품 현황 */}
        {activeTab === "product" && (
          <ProductStats dashboardStats={dashboardStats} />
        )}

        {/* 마켓 현황 */}
        {activeTab === "market" && (
          <MarketStats marketStats={marketStats} />
        )}

        {/* 주문 현황 */}
        {activeTab === "order" && (
          <OrderStats dashboardStats={dashboardStats} />
        )}
      </div>
    </div>
  );
}

function ProductStats({ dashboardStats }: any) {
  const p = dashboardStats?.products || {};

  return (
    <div className="space-y-3">
      <StatTable
        title="데이터 처리 총량 (Items)"
        data={[
          {
            label: "전체 수집 (RAW)",
            value: p.total_raw || 0,
            icon: <CheckCircle className="h-3 w-3 text-primary" />,
            progress: 100,
            description: "전체 수집 원본 데이터 명세",
          },
          {
            label: "최종 가공 완료 (Products)",
            value: p.refinement_completed || 0,
            icon: <CheckCircle className="h-3 w-3 text-success" />,
            progress: p.total_raw > 0 ? (p.refinement_completed / p.total_raw) * 100 : 0,
            description: "마켓 등록 즉시 가능 수량",
          },
          {
            label: "합계 재고 수량 (Stock)",
            value: p.total_stock || 0,
            icon: <CheckCircle className="h-3 w-3 text-warning" />,
            description: "DB 내 모든 리스팅의 가용 재고 총합",
          },
          {
            label: "스케일 도달 (Step 3)",
            value: p.lifecycle_stages?.step_3 || 0,
            icon: <CheckCircle className="h-3 w-3 text-info" />,
            description: "검증이 완료된 고효율 주력 상품",
          },
        ]}
      />
      <StatTable
        title="1단계: 소싱 (Candidate Discovery)"
        data={[
          {
            label: "전체 수집 (RAW)",
            value: p.total_raw || 0,
            icon: <CheckCircle className="h-3 w-3 text-muted-foreground" />,
          },
          {
            label: "소싱 대기 (PENDING)",
            value: p.sourcing_pending || 0,
            icon: <CheckCircle className="h-3 w-3 text-warning" />,
            progress: p.total_raw > 0 ? (p.sourcing_pending / p.total_raw) * 100 : 0,
          },
          {
            label: "소싱 승인 (APPROVED)",
            value: p.sourcing_approved || 0,
            icon: <CheckCircle className="h-3 w-3 text-success" />,
            progress: p.total_raw > 0 ? (p.sourcing_approved / p.total_raw) * 100 : 0,
          },
        ]}
      />
      <StatTable
        title="2단계: 가공 (AI Optimization)"
        data={[
          {
            label: "가공 대기",
            value: p.refinement_pending || 0,
            icon: <CheckCircle className="h-3 w-3 text-muted-foreground" />,
          },
          {
            label: "가공 중",
            value: p.refinement_processing || 0,
            icon: <CheckCircle className="h-3 w-3 text-info" />,
          },
          {
            label: "승인 대기",
            value: p.refinement_approval_pending || 0,
            icon: <ShieldCheck className="h-3 w-3 text-warning" />,
          },
          {
            label: "가공 실패",
            value: p.refinement_failed || 0,
            icon: <CheckCircle className="h-3 w-3 text-destructive" />,
            description: "데이터 정합성 부족 건",
          },
        ]}
      />
      <StatTable
        title="3단계: 리스팅 (Final Products)"
        data={[
          {
            label: "가공 완료",
            value: p.refinement_completed || 0,
            icon: <CheckCircle className="h-3 w-3 text-warning" />,
            description: "최적화 완료 상품 수",
          },
          {
            label: "탐색 단계 (Step 1)",
            value: p.lifecycle_stages?.step_1 || 0,
            icon: <CheckCircle className="h-3 w-3 text-info" />,
            description: "신규 등록 및 반응 확인 중",
          },
          {
            label: "성과 발생 상품",
            value: (p.lifecycle_stages?.step_2 || 0) + (p.lifecycle_stages?.step_3 || 0),
            icon: <CheckCircle className="h-3 w-3 text-success" />,
            description: "검증 또는 스케일 도달 상품",
          },
        ]}
      />
    </div>
  );
}

function MarketStats({ marketStats }: any) {
  const columns: TableColumn<any>[] = [
    {
      key: "market_code",
      title: "마켓 코드",
      width: "20%",
      render: (value) => (
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-success animate-pulse" />
          <span className="text-[11px] font-medium">{value}</span>
        </div>
      ),
    },
    {
      key: "account_name",
      title: "계정명",
      width: "40%",
      render: (value) => <span className="text-[11px]">{value}</span>,
    },
    {
      key: "listing_count",
      title: "리스팅 수",
      align: "right",
      width: "20%",
      render: (value) => <span className="font-semibold text-xs">{value.toLocaleString()}</span>,
    },
    {
      key: "percentage",
      title: "비율",
      align: "right",
      width: "20%",
      render: (_, row) => {
        const total = marketStats.reduce((sum: number, m: any) => sum + m.listing_count, 0);
        const percentage = total > 0 ? ((row.listing_count / total) * 100).toFixed(1) : "0.0";
        return <span className="text-xs text-muted-foreground">{percentage}%</span>;
      },
    },
  ];

  return (
    <div className="border border-border rounded-sm bg-card">
      <div className="px-3 py-1.5 border-b border-border bg-muted/50">
        <span className="text-[11px] font-semibold text-foreground">마켓별 등록 현황</span>
      </div>
      <div className="p-2">
        <Table
          columns={columns}
          data={marketStats}
          compact={true}
          striped={true}
          hover={true}
          emptyMessage="마켓 데이터가 없습니다."
        />
      </div>
    </div>
  );
}

function OrderStats({ dashboardStats }: any) {
  const orders = dashboardStats?.orders || {};
  return (
    <StatTable
      title="주문 현황"
      data={[
        {
          label: "결제 완료",
          value: orders.payment_completed || 0,
          icon: <CheckCircle className="h-3 w-3 text-info" />,
        },
        {
          label: "배송 준비",
          value: orders.ready || 0,
          icon: <CheckCircle className="h-3 w-3 text-warning" />,
        },
        {
          label: "배송 중",
          value: orders.shipping || 0,
          icon: <CheckCircle className="h-3 w-3 text-primary" />,
        },
        {
          label: "배송 완료",
          value: orders.shipped || 0,
          icon: <CheckCircle className="h-3 w-3 text-success" />,
        },
      ]}
    />
  );
}
