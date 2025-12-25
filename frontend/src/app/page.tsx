"use client";

import { useEffect, useState, useRef } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { ShoppingBag, CheckCircle, Clock, Zap, Activity, ShieldCheck, Bot, Play, Pause, RefreshCw, AlertCircle, Search, Filter, Download, X, Settings, TrendingUp, PieChart, Bell } from "lucide-react";
import { motion } from "framer-motion";
import { HealthStatus } from "@/components/HealthStatus";

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 }
};

// 로그 필터 타입
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
  const [events, setEvents] = useState<any[]>([]);
  const [filteredEvents, setFilteredEvents] = useState<any[]>([]);
  const [marketStats, setMarketStats] = useState<any[]>([]);
  const [agentStatus, setAgentStatus] = useState<any>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

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

  const fetchStats = async () => {
    try {
      const res = await api.get("/products/stats");
      setStats(res.data);
    } catch (e) {
      console.error("Failed to fetch stats", e);
      setStats({ total: 0, pending: 0, completed: 0 });
    }
  };

  const fetchEvents = async () => {
    try {
      const res = await api.get("/orchestration/events?limit=50");
      setEvents(res.data);
      setLastUpdatedAt(new Date());

      // 최신 이벤트가 COMPLETE 또는 FAIL이 아니면 실행 중으로 판단
      if (res.data.length > 0) {
        const latest = res.data[0];
        if (latest.status === "START" || latest.status === "IN_PROGRESS") {
          setIsRunning(true);
          updateOrchestrationProgress(latest);
        } else if (latest.step === "COMPLETE" || latest.status === "SUCCESS") {
          setIsRunning(false);
          setOrchestrationProgress({ currentStep: "", progress: 0, totalSteps: 0 });
        }

        // FAIL 상태 알림
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
  };

  const updateOrchestrationProgress = (latestEvent: any) => {
    const steps = ["PLANNING", "OPTIMIZATION", "SOURCING", "LISTING", "PREMIUM", "COMPLETE"];
    const currentIndex = steps.indexOf(latestEvent.step);
    setOrchestrationProgress({
      currentStep: latestEvent.step,
      progress: currentIndex >= 0 ? (currentIndex / (steps.length - 1)) * 100 : 0,
      totalSteps: steps.length
    });
  };

  const fetchMarketStats = async () => {
    try {
      const res = await api.get("/market/stats");
      setMarketStats(res.data);
    } catch (e) {
      console.error("Failed to fetch market stats", e);
    }
  };

  const fetchAgentStatus = async () => {
    try {
      const res = await api.get("/orchestration/agents/status");
      setAgentStatus(res.data);
    } catch (e) {
      console.error("Failed to fetch agent status", e);
    }
  };

  const fetchSettings = async () => {
    try {
      const res = await api.get("/settings/orchestrator");
      setSettings(res.data || settings);
    } catch (e) {
      console.error("Failed to fetch settings", e);
    }
  };

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

  const addNotification = (notification: any) => {
    setNotifications(prev => [notification, ...prev].slice(0, 10));
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

  // Auto scroll logs
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredEvents, autoScroll]);

  useEffect(() => {
    fetchStats();
    fetchEvents();
    fetchMarketStats();
    fetchAgentStatus();
    fetchSettings();

    // 5초마다 통계 및 이벤트 갱신
    const interval = setInterval(() => {
      fetchStats();
      fetchEvents();
      fetchMarketStats();
      fetchAgentStatus();
    }, 5000);

    return () => clearInterval(interval);
  }, []);

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

      // 10초 동안 Running 상태 유지 (시각적 효과)
      setTimeout(() => {
        setIsRunning(false);
        fetchStats();
      }, 10000);
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

  const exportLogs = () => {
    const dataStr = JSON.stringify(filteredEvents, null, 2);
    const dataUri = 'data:application/json;charset=utf-8,' + encodeURIComponent(dataStr);
    const exportName = 'orchestration_logs.json';
    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportName);
    linkElement.click();
  };

  const clearNotifications = () => {
    setNotifications([]);
  };

  // 진행률 계산
  const processingRate = stats.total > 0 ? ((stats.completed / stats.total) * 100).toFixed(1) : 0;
  const pendingRate = stats.total > 0 ? ((stats.pending / stats.total) * 100).toFixed(1) : 0;

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="show"
      className="space-y-10 py-6"
    >
      {/* Header */}
      <div className="flex flex-col gap-2">
        <motion.div variants={item} className="flex items-center justify-between">
          <h1 className="text-4xl font-black tracking-tight bg-gradient-to-r from-foreground to-foreground/60 bg-clip-text text-transparent">
            대시보드
          </h1>
          <div className="flex items-center gap-3">
            {/* 알림 버튼 */}
            <div className="relative">
              <Button
                variant="outline"
                size="icon"
                onClick={() => setShowNotifications(!showNotifications)}
                className="relative"
              >
                <Bell className="h-4 w-4" />
                {notifications.length > 0 && (
                  <span className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-red-500 text-[10px] font-bold flex items-center justify-center text-white">
                    {notifications.length}
                  </span>
                )}
              </Button>
              {showNotifications && (
                <div className="absolute right-0 top-12 w-80 bg-background border border-border rounded-lg shadow-xl z-50">
                  <div className="p-3 border-b border-border flex items-center justify-between">
                    <span className="text-sm font-bold">알림</span>
                    <Button variant="ghost" size="sm" onClick={clearNotifications} className="text-xs">
                      모두 지우기
                    </Button>
                  </div>
                  <div className="max-h-64 overflow-y-auto">
                    {notifications.length > 0 ? (
                      notifications.map((notif, i) => (
                        <div key={i} className={`p-3 border-b border-border/50 ${notif.type === "error" ? "bg-red-50" : "bg-background"}`}>
                          <div className="flex items-start gap-2">
                            {notif.type === "error" ? <AlertCircle className="h-4 w-4 text-red-500 shrink-0" /> : <Activity className="h-4 w-4 text-primary shrink-0" />}
                            <div className="flex-1">
                              <div className="text-xs font-bold">{notif.title}</div>
                              <div className="text-[10px] text-muted-foreground">{notif.message}</div>
                              <div className="text-[10px] text-muted-foreground mt-1">{new Date(notif.time).toLocaleTimeString()}</div>
                            </div>
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="p-4 text-center text-xs text-muted-foreground">알림이 없습니다.</div>
                    )}
                  </div>
                </div>
              )}
            </div>
            {/* 설정 버튼 */}
            <Button
              variant="outline"
              size="icon"
              onClick={() => setShowSettings(!showSettings)}
            >
              <Settings className="h-4 w-4" />
            </Button>
          </div>
        </motion.div>
        <motion.p variants={item} className="text-muted-foreground font-medium">
          드랍쉬핑 자동화 시스템의 현재 가동 상태 및 통계입니다.
        </motion.p>
      </div>

      {/* 설정 패널 */}
      {showSettings && (
        <motion.div variants={item}>
          <Card className="border-primary/20 bg-accent/10">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                오케스트레이션 설정
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-2">
                  <label className="text-sm font-medium">일일 등록 한도</label>
                  <Input
                    type="number"
                    value={settings.listing_limit}
                    onChange={(e) => setSettings({ ...settings, listing_limit: parseInt(e.target.value) || 0 })}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">키워드 소싱 한도</label>
                  <Input
                    type="number"
                    value={settings.sourcing_keyword_limit}
                    onChange={(e) => setSettings({ ...settings, sourcing_keyword_limit: parseInt(e.target.value) || 0 })}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">지속 모드</label>
                  <Select
                    value={settings.continuous_mode ? "true" : "false"}
                    onChange={(e) => setSettings({ ...settings, continuous_mode: e.target.value === "true" })}
                    options={[
                      { value: "true", label: "활성화" },
                      { value: "false", label: "비활성화" }
                    ]}
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setShowSettings(false)}>
                  취소
                </Button>
                <Button onClick={updateSettings}>
                  저장
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* 통계 카드 */}
      <motion.div variants={container} className="grid gap-6 md:grid-cols-4">
        <motion.div variants={item}>
          <Card className="overflow-hidden group">
            <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
              <ShoppingBag className="h-24 w-24" />
            </div>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-bold uppercase tracking-widest text-muted-foreground">전체 상품</CardTitle>
              <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <ShoppingBag className="h-4 w-4 text-primary" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black">{stats.total.toLocaleString()}</div>
              <div className="mt-2 flex items-center gap-2">
                <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                  <div className="h-full bg-primary transition-all" style={{ width: '100%' }} />
                </div>
                <span className="text-xs font-bold text-emerald-500">100%</span>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div variants={item}>
          <Card className="overflow-hidden group">
            <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
              <Clock className="h-24 w-24" />
            </div>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-bold uppercase tracking-widest text-muted-foreground">가공 대기중</CardTitle>
              <div className="h-8 w-8 rounded-lg bg-amber-500/10 flex items-center justify-center">
                <Clock className="h-4 w-4 text-amber-500" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black text-amber-500">{stats.pending.toLocaleString()}</div>
              <div className="mt-2 flex items-center gap-2">
                <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                  <div className="h-full bg-amber-500 transition-all" style={{ width: `${pendingRate}%` }} />
                </div>
                <span className="text-xs font-bold text-amber-500">{pendingRate}%</span>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div variants={item}>
          <Card className="overflow-hidden group">
            <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
              <CheckCircle className="h-24 w-24" />
            </div>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-bold uppercase tracking-widest text-muted-foreground">쿠팡 등록 완료</CardTitle>
              <div className="h-8 w-8 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                <CheckCircle className="h-4 w-4 text-emerald-500" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black text-emerald-500">{stats.completed.toLocaleString()}</div>
              <div className="mt-2 flex items-center gap-2">
                <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                  <div className="h-full bg-emerald-500 transition-all" style={{ width: `${processingRate}%` }} />
                </div>
                <span className="text-xs font-bold text-emerald-500">{processingRate}%</span>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div variants={item}>
          <Card className="overflow-hidden group">
            <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
              <TrendingUp className="h-24 w-24" />
            </div>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-bold uppercase tracking-widest text-muted-foreground">오늘 등록</CardTitle>
              <div className="h-8 w-8 rounded-lg bg-blue-500/10 flex items-center justify-center">
                <TrendingUp className="h-4 w-4 text-blue-500" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-black text-blue-500">{(stats as any).today_count?.toLocaleString() || 0}</div>
              <div className="mt-2 text-xs font-bold text-muted-foreground">
                목표: {settings.listing_limit.toLocaleString()}개
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </motion.div>

      {/* Health Check Dashboard Section */}
      <motion.div variants={item}>
        <HealthStatus />
      </motion.div>

      {/* Market Account Stats Section */}
      <motion.div variants={item}>
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {marketStats.map((ms) => (
            <Card key={ms.account_id} className="border-l-4 border-l-primary bg-accent/10">
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-bold uppercase tracking-tighter text-muted-foreground flex items-center justify-between">
                  {ms.market_code}
                  <Activity className="h-3 w-3 text-emerald-500" />
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-lg font-bold truncate mb-1">{ms.account_name}</div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-black text-primary">{ms.listing_count.toLocaleString()}</span>
                  <span className="text-xs font-medium text-muted-foreground">개 등록됨</span>
                </div>
              </CardContent>
            </Card>
          ))}
          {marketStats.length === 0 && (
            <Card className="col-span-full border-dashed bg-transparent flex items-center justify-center p-6 text-muted-foreground italic text-sm">
              등록된 마켓 계정이 없습니다.
            </Card>
          )}
        </div>
      </motion.div>

      {/* AI Orchestration Control Panel */}
      <motion.div variants={item}>
        <Card className="bg-gradient-to-br from-primary/5 to-transparent border-primary/20 overflow-hidden relative">
          <div className="absolute top-0 right-0 p-8 opacity-5">
            <Bot className="h-32 w-32" />
          </div>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-xl">
              <Zap className="h-6 w-6 text-primary animate-pulse" />
              AI 오케스트레이션 제어 센터 (Step 1)
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {/* 진행률 표시 */}
            {isRunning && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{orchestrationProgress.currentStep}</span>
                  <span className="text-muted-foreground">{Math.round(orchestrationProgress.progress)}%</span>
                </div>
                <div className="h-2 bg-muted rounded-full overflow-hidden">
                  <motion.div
                    className="h-full bg-primary"
                    initial={{ width: 0 }}
                    animate={{ width: `${orchestrationProgress.progress}%` }}
                    transition={{ duration: 0.5 }}
                  />
                </div>
              </div>
            )}
            <div className="flex flex-col md:flex-row items-center gap-6">
              <div className="flex-1 space-y-2">
                <p className="text-sm font-medium text-muted-foreground">
                  AI가 자동으로 시장 트렌드를 분석하고, 상품을 소싱하여 1단계 가공(상품명 최적화) 후 등록된 모든 마켓에 전송합니다.
                </p>
                <div className="flex items-center gap-4">
                  <div className={`px-2 py-1 rounded text-[10px] font-bold uppercase tracking-widest ${isRunning ? 'bg-emerald-500/20 text-emerald-500 animate-pulse' : 'bg-muted text-muted-foreground'}`}>
                    {isRunning ? 'System Running' : 'System Ready'}
                  </div>
                  <span className="text-xs text-muted-foreground italic">대기 중인 최적화 사이클: 즉시 실행 가능</span>
                </div>
              </div>
              <div className="flex items-center gap-3 relative z-10">
                <Button
                  onClick={() => handleRunCycle(true)}
                  disabled={isLoading || isRunning}
                  variant="outline"
                  className="rounded-2xl font-bold bg-accent hover:bg-accent/80 transition-all px-6 py-6"
                >
                  <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                  테스트 가동 (Dry Run)
                </Button>
                <Button
                  onClick={() => handleRunCycle(false)}
                  disabled={isLoading || isRunning}
                  className="rounded-2xl bg-primary text-primary-foreground hover:shadow-lg hover:shadow-primary/30 font-black transition-all px-8 py-6 active:scale-95"
                >
                  {isRunning ? (
                    <>
                      <Pause className="mr-2 h-4 w-4 fill-current" />
                      가동 중...
                    </>
                  ) : (
                    <>
                      <Play className="mr-2 h-4 w-4 fill-current" />
                      자동 운영 시작
                    </>
                  )}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      <motion.div variants={container} className="grid gap-6 md:grid-cols-2 lg:grid-cols-7">
        {/* 로그 섹션 */}
        <motion.div variants={item} className="col-span-full">
          <Card className="border-primary/20 overflow-hidden bg-zinc-950 text-zinc-100 shadow-2xl">
            <CardHeader className="border-b border-primary/20 py-3 flex flex-row items-center justify-between">
              <CardTitle className="text-sm font-black flex items-center gap-2 text-primary tracking-widest uppercase">
                <div className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-primary"></span>
                </div>
                Live AI Orchestration Logs
              </CardTitle>
              <div className="flex items-center gap-4">
                {lastUpdatedAt && (
                  <span className="text-[10px] font-bold text-zinc-500 italic">
                    Updated: {lastUpdatedAt.toLocaleTimeString()}
                  </span>
                )}
                <div className="flex gap-1.5">
                  <div className="h-2.5 w-2.5 rounded-full bg-red-500/50" />
                  <div className="h-2.5 w-2.5 rounded-full bg-amber-500/50" />
                  <div className="h-2.5 w-2.5 rounded-full bg-emerald-500/50" />
                </div>
              </div>
            </CardHeader>
            {/* 로그 필터 및 검색 */}
            <div className="border-b border-primary/20 p-3 flex flex-wrap gap-3 items-center">
              <div className="flex items-center gap-2 flex-1 min-w-[200px]">
                <Search className="h-4 w-4 text-zinc-500" />
                <Input
                  placeholder="로그 검색..."
                  value={logFilter.search}
                  onChange={(e) => setLogFilter({ ...logFilter, search: e.target.value })}
                  className="bg-zinc-900 border-zinc-700 text-zinc-100 text-sm"
                />
              </div>
              <Select
                value={logFilter.step}
                onChange={(e) => setLogFilter({ ...logFilter, step: e.target.value })}
                options={[
                  { value: "ALL", label: "모든 단계" },
                  { value: "PLANNING", label: "PLANNING" },
                  { value: "OPTIMIZATION", label: "OPTIMIZATION" },
                  { value: "SOURCING", label: "SOURCING" },
                  { value: "LISTING", label: "LISTING" },
                  { value: "PREMIUM", label: "PREMIUM" }
                ]}
                className="w-[150px]"
              />
              <Select
                value={logFilter.status}
                onChange={(e) => setLogFilter({ ...logFilter, status: e.target.value })}
                options={[
                  { value: "ALL", label: "모든 상태" },
                  { value: "START", label: "START" },
                  { value: "IN_PROGRESS", label: "IN_PROGRESS" },
                  { value: "SUCCESS", label: "SUCCESS" },
                  { value: "FAIL", label: "FAIL" }
                ]}
                className="w-[120px]"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAutoScroll(!autoScroll)}
                className={autoScroll ? "bg-primary/20" : ""}
              >
                <Activity className="h-4 w-4 mr-2" />
                {autoScroll ? "스크롤 ON" : "스크롤 OFF"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={exportLogs}
              >
                <Download className="h-4 w-4 mr-2" />
                내보내기
              </Button>
              {(logFilter.step !== "ALL" || logFilter.status !== "ALL" || logFilter.search) && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setLogFilter({ step: "ALL", status: "ALL", search: "" })}
                >
                  <X className="h-4 w-4 mr-2" />
                  필터 초기화
                </Button>
              )}
            </div>
            <CardContent className="p-0">
              <div ref={scrollRef} className="h-[400px] overflow-y-auto p-4 font-mono text-[13px] leading-relaxed space-y-1 custom-scrollbar scroll-smooth">
                {filteredEvents.length > 0 ? (
                  filteredEvents.slice().reverse().map((event, i) => (
                    <div key={event.id || i} className="flex gap-3 hover:bg-white/5 transition-colors py-0.5 px-2 rounded group border-l-2 border-transparent hover:border-primary/40">
                      <span className="text-zinc-500 shrink-0 font-bold">
                        [{new Date(event.created_at).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}]
                      </span>
                      <span className={`shrink-0 font-black w-14 ${event.status === "FAIL" ? "text-red-500" :
                        event.status === "START" ? "text-blue-500" :
                          event.status === "SUCCESS" ? "text-emerald-500" :
                            "text-amber-500"
                        }`}>
                        {event.status}
                      </span>
                      <span className="text-zinc-400 shrink-0 opacity-50">|</span>
                      <span className="text-zinc-600 shrink-0 w-20 font-bold font-sans tracking-tighter uppercase text-[10px] mt-0.5">
                        {event.step}
                      </span>
                      <span className="text-zinc-300 break-all group-hover:text-white transition-colors">
                        {event.message}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-zinc-600 italic">
                    <RefreshCw className="h-8 w-8 mb-4 animate-spin opacity-20" />
                    <p>연결 대기 중... 로그를 기다리고 있습니다.</p>
                  </div>
                )}
                {/* Auto scroll anchor */}
                <div id="log-bottom" />
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* 에이전트 상태 섹션 */}
        <motion.div variants={item} className="col-span-3">
          <Card className="h-full">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bot className="h-5 w-5 text-primary" />
                에이전트 상태
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-6">
                <div className="relative p-4 rounded-2xl bg-gradient-to-br from-emerald-500/10 to-transparent border border-emerald-500/20">
                  <div className="flex items-center mb-2">
                    <div className="relative flex h-3 w-3 mr-3">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                    </div>
                    <span className="text-sm font-bold">Sourcing Agent</span>
                    <span className="ml-auto px-2 py-0.5 rounded-full bg-emerald-500/20 text-[10px] font-black uppercase text-emerald-600 tracking-tighter">
                      {agentStatus?.sourcing?.status || "Healthy"}
                    </span>
                  </div>
                  <div className="text-xs text-muted-foreground font-medium">
                    {agentStatus?.sourcing?.message || "현재 새로운 상품 후보군을 탐색하고 있습니다."}
                  </div>
                  {agentStatus?.sourcing?.queue_size !== undefined && (
                    <div className="mt-2 text-xs text-muted-foreground">
                      대기 큐: {agentStatus.sourcing.queue_size}개
                    </div>
                  )}
                </div>

                <div className="relative p-4 rounded-2xl bg-gradient-to-br from-primary/10 to-transparent border border-primary/20">
                  <div className="flex items-center mb-2">
                    <div className="relative flex h-3 w-3 mr-3">
                      <span className="animate-pulse absolute inline-flex h-full w-full rounded-full bg-primary/40 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-3 w-3 bg-primary"></span>
                    </div>
                    <span className="text-sm font-bold">Processing Agent</span>
                    <span className="ml-auto px-2 py-0.5 rounded-full bg-primary/20 text-[10px] font-black uppercase text-primary tracking-tighter">
                      {agentStatus?.processing?.status || "Live"}
                    </span>
                  </div>
                  <div className="text-xs text-muted-foreground font-medium">
                    {agentStatus?.processing?.message || "데이터 SEO 최적화 및 이미지 가공 엔진 대기 중"}
                  </div>
                  {agentStatus?.processing?.queue_size !== undefined && (
                    <div className="mt-2 text-xs text-muted-foreground">
                      대기 큐: {agentStatus.processing.queue_size}개
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* 마켓별 등록 현황 */}
        <motion.div variants={item} className="col-span-4">
          <Card className="h-full">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <PieChart className="h-5 w-5 text-primary" />
                마켓별 등록 현황
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {marketStats.map((ms) => {
                  const total = marketStats.reduce((sum, m) => sum + m.listing_count, 0);
                  const percentage = total > 0 ? ((ms.listing_count / total) * 100).toFixed(1) : 0;
                  return (
                    <div key={ms.account_id} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium">{ms.market_code}</span>
                        <span className="text-muted-foreground">{ms.listing_count.toLocaleString()}개 ({percentage}%)</span>
                      </div>
                      <div className="h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary transition-all"
                          style={{ width: `${percentage}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
                {marketStats.length === 0 && (
                  <div className="text-center text-sm text-muted-foreground py-8">
                    데이터가 없습니다.
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </motion.div>
    </motion.div>
  );
}
