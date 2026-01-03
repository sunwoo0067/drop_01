"use client";

import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Table, TableColumn } from "@/components/ui/Table";
import { DashboardToolbar } from "./dashboard/DashboardToolbar";
import { StatTable } from "./dashboard/StatTable";
import { OrchestrationControl } from "./dashboard/OrchestrationControl";
import { LogViewer } from "./dashboard/LogViewer";
import { ShieldCheck, CheckCircle, AlertTriangle, RotateCcw, FileText, Activity } from "lucide-react";

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
  const [activeTab, setActiveTab] = useState("ai");
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

  // 전문가 모드 설정
  const [isExpertMode, setIsExpertMode] = useState(false);

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
  const marketsSummary = (dashboardStats?.markets && dashboardStats.markets.length > 0)
    ? dashboardStats.markets
    : marketStats;
  const listingTotal = marketsSummary.reduce((sum: number, row: any) => sum + (row.listing_count || 0), 0);
  const supplierTotal = p.total_raw ?? stats.total ?? 0;
  const sourcingTotal = (p.sourcing_pending || 0) + (p.sourcing_approved || 0);
  const processingTotal = (p.refinement_pending || 0)
    + (p.refinement_processing || 0)
    + (p.refinement_approval_pending || 0)
    + (p.refinement_failed || 0)
    + (p.refinement_completed || 0);
  const latestEvent = events[0];
  const gatingSummary = gatingReport?.summary || {};
  const sourcingPendingRate = supplierTotal > 0 ? ((p.sourcing_pending || 0) / supplierTotal) * 100 : 0;
  const processingFailedRate = processingTotal > 0 ? ((p.refinement_failed || 0) / processingTotal) * 100 : 0;
  const retryRate = listingTotal > 0 ? ((gatingSummary.retryCount || 0) / listingTotal) * 100 : 0;
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
  const kpiHighlights = [
    {
      label: "소싱 대기 비중",
      value: sourcingPendingRate,
      detail: `${(p.sourcing_pending || 0).toLocaleString()} / ${supplierTotal.toLocaleString()}`,
      tone: "text-warning",
    },
    {
      label: "가공 실패 비중",
      value: processingFailedRate,
      detail: `${(p.refinement_failed || 0).toLocaleString()} / ${processingTotal.toLocaleString()}`,
      tone: "text-destructive",
    },
    {
      label: "쿠팡 재시도 비중",
      value: retryRate,
      detail: `${(gatingSummary.retryCount || 0).toLocaleString()} / ${listingTotal.toLocaleString()}`,
      tone: "text-info",
    },
  ];

  return (
    <div className="space-y-3">
      {/* 툴바 */}
      <div className="flex items-center justify-between gap-3">
        <DashboardToolbar
          isLoading={isLoading}
          isRunning={isRunning}
          onRunCycle={() => handleRunCycle(true)}
          onToggleSettings={() => setShowSettings(!showSettings)}
          onToggleNotifications={() => setShowNotifications(!showNotifications)}
          notificationCount={notifications.length}
        />
        <div className="flex items-center gap-2 bg-card border border-border px-3 py-1 rounded-sm shadow-sm">
          <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">전문가 모드</span>
          <button
            onClick={() => setIsExpertMode(!isExpertMode)}
            className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 ${isExpertMode ? 'bg-primary' : 'bg-muted'}`}
          >
            <span
              className={`pointer-events-none block h-4 w-4 rounded-full bg-background shadow-lg ring-0 transition-transform ${isExpertMode ? 'translate-x-4' : 'translate-x-0'}`}
            />
          </button>
        </div>
      </div>

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

      {/* 핵심 요약 + 에이전트 진행 */}
      <div className="grid gap-3 lg:grid-cols-[1.4fr,0.6fr]">
        <Card className="border border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs">전체 흐름 요약</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "공급사 상품 전체", value: supplierTotal, hint: "RAW 기준" },
              { label: "소싱 전체", value: sourcingTotal, hint: "PENDING + APPROVED" },
              { label: "가공 전체", value: processingTotal, hint: "전 단계 합계" },
              { label: "상품 등록 전체", value: listingTotal, hint: "마켓 리스팅 합계" },
            ].map((row) => (
              <div key={row.label} className="rounded-sm border border-border/60 bg-muted/30 px-3 py-2">
                <div className="text-[10px] text-muted-foreground">{row.label}</div>
                <div className="text-lg font-semibold">{row.value.toLocaleString()}</div>
                <div className="text-[9px] text-muted-foreground">{row.hint}</div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="border border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs">AI 에이전트 진행</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between text-[11px]">
              <div className="flex items-center gap-2">
                <span className={`h-2.5 w-2.5 rounded-full ${isRunning ? "bg-emerald-500" : "bg-muted-foreground"}`} />
                <span className="font-semibold">{isRunning ? "실행 중" : "대기"}</span>
              </div>
              <span className="text-muted-foreground">{lastUpdatedAt ? lastUpdatedAt.toLocaleTimeString() : "-"}</span>
            </div>
            <div>
              <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                <span>현재 단계</span>
                <span>{latestEvent?.step || "-"}</span>
              </div>
              <div className="mt-1 h-2 rounded-full bg-muted/60">
                <div
                  className="h-2 rounded-full bg-primary transition-all"
                  style={{ width: `${orchestrationProgress.progress || 0}%` }}
                />
              </div>
              <div className="mt-1 text-[10px] text-muted-foreground">
                {latestEvent?.message || "진행 중인 이벤트가 없습니다."}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 탭/필터 바 */}
      <div className="space-y-3">
        {/* 탭/필터 바 (전문가 모드 전용) */}
        {isExpertMode ? (
          <div className="space-y-3 animate-in fade-in slide-in-from-top-2 duration-500">
            <div className="flex items-center justify-between px-3 py-2 border border-border bg-card rounded-sm shadow-sm">
              <div className="flex gap-2 text-[11px]">
                <Button
                  variant={activeTab === "ai" ? "primary" : "ghost"}
                  size="xs"
                  onClick={() => setActiveTab("ai")}
                >
                  AI 진행
                </Button>
                <Button
                  variant={activeTab === "sourcing" ? "primary" : "ghost"}
                  size="xs"
                  onClick={() => setActiveTab("sourcing")}
                >
                  공급사/소싱
                </Button>
                <Button
                  variant={activeTab === "processing" ? "primary" : "ghost"}
                  size="xs"
                  onClick={() => setActiveTab("processing")}
                >
                  가공
                </Button>
                <Button
                  variant={activeTab === "listing" ? "primary" : "ghost"}
                  size="xs"
                  onClick={() => setActiveTab("listing")}
                >
                  등록
                </Button>
                <Button
                  variant={activeTab === "order" ? "primary" : "ghost"}
                  size="xs"
                  onClick={() => setActiveTab("order")}
                >
                  주문
                </Button>
                <Button
                  variant={activeTab === "logs" ? "primary" : "ghost"}
                  size="xs"
                  onClick={() => setActiveTab("logs")}
                >
                  로그
                </Button>
              </div>
              <div className="text-[9px] text-muted-foreground bg-muted px-2 py-1 rounded-sm">
                상태: 전문가 분석 모드
              </div>
            </div>

            {/* AI 진행 */}
            {activeTab === "ai" && (
              <div className="space-y-3">
                <OrchestrationControl
                  isRunning={isRunning}
                  isLoading={isLoading}
                  orchestrationProgress={orchestrationProgress}
                  onRunCycle={handleRunCycle}
                />
                <Card className="border border-border">
                  <CardHeader className="py-2">
                    <CardTitle className="text-xs">KPI 하이라이트</CardTitle>
                  </CardHeader>
                  <CardContent className="grid gap-2 sm:grid-cols-3">
                    {kpiHighlights.map((item) => (
                      <div key={item.label} className="rounded-sm border border-border/60 bg-muted/30 px-3 py-2">
                        <div className="text-[10px] text-muted-foreground">{item.label}</div>
                        <div className={`text-lg font-semibold ${item.tone}`}>
                          {item.value.toFixed(1)}%
                        </div>
                        <div className="text-[9px] text-muted-foreground">{item.detail}</div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
                <div className="grid gap-3 md:grid-cols-[1fr,1fr]">
                  <StatTable title="쿠팡 분기 현황" data={gatingStats} />
                  <Card className="border border-border">
                    <CardHeader className="py-2">
                      <CardTitle className="text-xs">최근 이벤트</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {events.slice(0, 6).map((row, index) => (
                        <div
                          key={`${row.step}-${row.status}-${index}`}
                          className="flex items-start justify-between gap-3 rounded-sm border border-border/50 bg-background px-2 py-1.5"
                        >
                          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                            <Activity className="h-3 w-3 text-primary" />
                            <span className="font-semibold">{row.step}</span>
                            <span>{row.status}</span>
                          </div>
                          <span className="text-[10px] text-muted-foreground line-clamp-1 text-right max-w-[60%]">
                            {row.message || "-"}
                          </span>
                        </div>
                      ))}
                      {events.length === 0 && (
                        <div className="text-center text-[11px] text-muted-foreground py-4">
                          이벤트가 없습니다.
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </div>
            )}

            {/* 공급사/소싱 */}
            {activeTab === "sourcing" && (
              <StatTable
                title="공급사/소싱 상세"
                data={[
                  {
                    label: "공급사 전체 수량 (RAW)",
                    value: supplierTotal,
                    icon: <CheckCircle className="h-3 w-3 text-primary" />,
                    description: "SupplierItemRaw 기준",
                  },
                  {
                    label: "소싱 대기",
                    value: p.sourcing_pending || 0,
                    icon: <CheckCircle className="h-3 w-3 text-warning" />,
                  },
                  {
                    label: "소싱 승인",
                    value: p.sourcing_approved || 0,
                    icon: <CheckCircle className="h-3 w-3 text-success" />,
                  },
                ]}
              />
            )}

            {/* 가공 */}
            {activeTab === "processing" && (
              <StatTable
                title="가공 단계 상세"
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
                  },
                  {
                    label: "가공 완료",
                    value: p.refinement_completed || 0,
                    icon: <CheckCircle className="h-3 w-3 text-success" />,
                  },
                ]}
              />
            )}

            {/* 등록 */}
            {activeTab === "listing" && (
              <MarketStats marketStats={marketsSummary} />
            )}

            {/* 주문 현황 */}
            {activeTab === "order" && (
              <OrderStats dashboardStats={dashboardStats} />
            )}

            {/* 로그 */}
            {activeTab === "logs" && (
              <LogViewer
                filteredEvents={filteredEvents}
                logFilter={logFilter}
                setLogFilter={setLogFilter}
                autoScroll={autoScroll}
                setAutoScroll={setAutoScroll}
              />
            )}
          </div>
        ) : (
          <div className="grid gap-3 animate-in fade-in duration-700">
            <Card className="border border-border/50 bg-gradient-to-br from-card to-muted/10">
              <CardContent className="p-8 flex flex-col items-center justify-center space-y-4">
                <div className="relative">
                  <div className={`absolute inset-0 rounded-full animate-ping opacity-20 ${isRunning ? 'bg-emerald-500' : 'bg-muted-foreground'}`} />
                  <div className={`relative h-16 w-16 rounded-full flex items-center justify-center ${isRunning ? 'bg-emerald-500 text-white shadow-[0_0_20px_rgba(16,185,129,0.5)]' : 'bg-muted text-muted-foreground'}`}>
                    <Activity className={`h-8 w-8 ${isRunning ? 'animate-pulse' : ''}`} />
                  </div>
                </div>
                <div className="text-center space-y-1">
                  <h3 className="text-xl font-black">{isRunning ? "AI 에이전트가 가동 중입니다" : "AI 에이전트가 대기 중입니다"}</h3>
                  <p className="text-sm text-muted-foreground">
                    {latestEvent?.message || "현재 시스템이 안정적인 상태로 운영되고 있습니다."}
                  </p>
                </div>
                {!isRunning && (
                  <Button size="lg" className="px-10 rounded-full font-bold shadow-lg shadow-primary/20" onClick={() => handleRunCycle(true)}>
                    자율 운영 시작하기
                  </Button>
                )}

                <div className="w-full max-w-2xl grid grid-cols-4 gap-4 mt-8 pt-8 border-t border-border/50">
                  <div className="text-center space-y-1">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase">발굴</p>
                    <p className="text-xl font-black">{p.sourcing_approved?.toLocaleString() || 0}</p>
                    <div className="h-1 w-full bg-muted rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500" style={{ width: `${Math.min(100, ((p.sourcing_approved || 0) / (p.sourcing_pending || 1)) * 100)}%` }} />
                    </div>
                  </div>
                  <div className="text-center space-y-1">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase">가공</p>
                    <p className="text-xl font-black">{p.refinement_completed?.toLocaleString() || 0}</p>
                    <div className="h-1 w-full bg-muted rounded-full overflow-hidden">
                      <div className="h-full bg-amber-500" style={{ width: `${Math.min(100, ((p.refinement_completed || 0) / (processingTotal || 1)) * 100)}%` }} />
                    </div>
                  </div>
                  <div className="text-center space-y-1">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase">등록</p>
                    <p className="text-xl font-black">{listingTotal?.toLocaleString() || 0}</p>
                    <div className="h-1 w-full bg-muted rounded-full overflow-hidden">
                      <div className="h-full bg-emerald-500" style={{ width: '85%' }} />
                    </div>
                  </div>
                  <div className="text-center space-y-1">
                    <p className="text-[10px] font-bold text-muted-foreground uppercase">주문</p>
                    <p className="text-xl font-black">{(dashboardStats?.orders?.payment_completed || 0).toLocaleString()}</p>
                    <div className="h-1 w-full bg-muted rounded-full overflow-hidden">
                      <div className="h-full bg-primary" style={{ width: '40%' }} />
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
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
