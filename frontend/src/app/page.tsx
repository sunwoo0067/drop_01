"use client";

import { useEffect, useState, useRef } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ShoppingBag, CheckCircle, Clock, Zap, Activity, ShieldCheck, Bot, Play, Pause, RefreshCw, AlertCircle } from "lucide-react";
import { motion } from "framer-motion";

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

export default function Home() {
  const [stats, setStats] = useState({
    total: 0,
    pending: 0,
    completed: 0
  });
  const [events, setEvents] = useState<any[]>([]);
  const [marketStats, setMarketStats] = useState<any[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

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
      const res = await api.get("/orchestration/events?limit=20");
      setEvents(res.data);
      setLastUpdatedAt(new Date());

      // 최신 이벤트가 COMPLETE 또는 FAIL이 아니면 실행 중으로 판단
      if (res.data.length > 0) {
        const latest = res.data[0];
        if (latest.status === "START" || latest.status === "IN_PROGRESS") {
          setIsRunning(true);
        } else if (latest.step === "COMPLETE" || latest.status === "SUCCESS") {
          setIsRunning(false);
        }
      }
    } catch (e) {
      console.error("Failed to fetch events", e);
    }
  };

  const fetchMarketStats = async () => {
    try {
      const res = await api.get("/market/stats");
      setMarketStats(res.data);
    } catch (e) {
      console.error("Failed to fetch market stats", e);
    }
  };

  useEffect(() => {
    fetchStats();
    fetchEvents();
    fetchMarketStats();

    // 5초마다 통계 및 이벤트 갱신
    const interval = setInterval(() => {
      fetchStats();
      fetchEvents();
      fetchMarketStats();
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  // Auto scroll logs
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  const handleRunCycle = async (dryRun: boolean = true) => {
    console.log(`Triggering orchestration cycle: dryRun=${dryRun}`);
    setIsLoading(true);
    try {
      await api.post(`/orchestration/run-cycle?dryRun=${dryRun}`);
      setIsRunning(true);
      alert(dryRun ? "테스트 가동(Dry Run)이 시작되었습니다. 실제 등록은 수행되지 않습니다." : "AI 자율 운영(Step 1)이 시작되었습니다. 소싱 및 등록이 백그라운드에서 진행됩니다.");

      // 10초 동안 Running 상태 유지 (시각적 효과)
      setTimeout(() => {
        setIsRunning(false);
        fetchStats();
      }, 10000);
    } catch (e) {
      console.error("Failed to run cycle", e);
      alert("AI 가동 요청에 실패했습니다. 서버 상태를 확인해주세요.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="show"
      className="space-y-10 py-6"
    >
      <div className="flex flex-col gap-2">
        <motion.h1 variants={item} className="text-4xl font-black tracking-tight bg-gradient-to-r from-foreground to-foreground/60 bg-clip-text text-transparent">
          대시보드
        </motion.h1>
        <motion.p variants={item} className="text-muted-foreground font-medium">
          드랍쉬핑 자동화 시스템의 현재 가동 상태 및 통계입니다.
        </motion.p>
      </div>

      <motion.div variants={container} className="grid gap-6 md:grid-cols-3">
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
              <div className="mt-2 flex items-center text-xs font-bold text-emerald-500">
                <Activity className="h-3 w-3 mr-1" />
                <span>실시간 수집 중</span>
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
              <div className="text-4xl font-black">{stats.pending.toLocaleString()}</div>
              <div className="mt-2 text-xs font-bold text-muted-foreground">
                AI 최적화 대기 물량
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
              <div className="mt-2 flex items-center text-xs font-bold text-muted-foreground">
                <ShieldCheck className="h-3 w-3 mr-1 text-emerald-500" />
                <span>안정적인 연동 상태</span>
              </div>
            </CardContent>
          </Card>
        </motion.div>
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
          <CardContent className="flex flex-col md:flex-row items-center gap-6">
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
          </CardContent>
        </Card>
      </motion.div>

      <motion.div variants={container} className="grid gap-6 md:grid-cols-2 lg:grid-cols-7">
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
            <CardContent className="p-0">
              <div ref={scrollRef} className="h-[400px] overflow-y-auto p-4 font-mono text-[13px] leading-relaxed space-y-1 custom-scrollbar scroll-smooth">
                {events.length > 0 ? (
                  events.slice().reverse().map((event, i) => (
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
                    <span className="ml-auto px-2 py-0.5 rounded-full bg-emerald-500/20 text-[10px] font-black uppercase text-emerald-600 tracking-tighter">Healthy</span>
                  </div>
                  <div className="text-xs text-muted-foreground font-medium">현재 새로운 상품 후보군을 탐색하고 있습니다.</div>
                </div>

                <div className="relative p-4 rounded-2xl bg-gradient-to-br from-primary/10 to-transparent border border-primary/20">
                  <div className="flex items-center mb-2">
                    <div className="relative flex h-3 w-3 mr-3">
                      <span className="animate-pulse absolute inline-flex h-full w-full rounded-full bg-primary/40 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-3 w-3 bg-primary"></span>
                    </div>
                    <span className="text-sm font-bold">Processing Agent</span>
                    <span className="ml-auto px-2 py-0.5 rounded-full bg-primary/20 text-[10px] font-black uppercase text-primary tracking-tighter">Live</span>
                  </div>
                  <div className="text-xs text-muted-foreground font-medium">데이터 SEO 최적화 및 이미지 가공 엔진 대기 중</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </motion.div>
    </motion.div>
  );
}
