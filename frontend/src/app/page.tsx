"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ShoppingBag, CheckCircle, Clock, Zap, Activity, ShieldCheck, Bot, Play, Pause, RefreshCw } from "lucide-react";
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
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const fetchStats = async () => {
    try {
      const res = await api.get("/products/stats");
      setStats(res.data);
    } catch (e) {
      console.error("Failed to fetch stats", e);
      setStats({ total: 0, pending: 0, completed: 0 });
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  const handleRunCycle = async (dryRun: boolean = true) => {
    setIsLoading(true);
    try {
      await api.post(`/orchestration/run-cycle?dryRun=${dryRun}`);
      setIsRunning(true);
      // 백그라운드 작업이므로 즉시 상태를 바꾸고 시각적 피드백 제공
      setTimeout(() => {
        setIsRunning(false);
        fetchStats();
      }, 5000); // 5초 후 running 상태 해제 (시뮬레이션)
    } catch (e) {
      console.error("Failed to run cycle", e);
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
            <div className="flex items-center gap-3">
              <button
                onClick={() => handleRunCycle(true)}
                disabled={isLoading || isRunning}
                className="flex items-center gap-2 px-6 py-3 rounded-2xl bg-accent hover:bg-accent/80 font-black text-sm transition-all disabled:opacity-50"
              >
                <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                테스트 가동 (Dry Run)
              </button>
              <button
                onClick={() => handleRunCycle(false)}
                disabled={isLoading || isRunning}
                className="flex items-center gap-2 px-8 py-3 rounded-2xl bg-primary text-primary-foreground hover:shadow-lg hover:shadow-primary/30 font-black text-sm transition-all disabled:opacity-50 active:scale-95"
              >
                {isRunning ? (
                  <>
                    <Pause className="h-4 w-4 fill-current" />
                    가동 중...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 fill-current" />
                    자동 운영 시작
                  </>
                )}
              </button>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      <motion.div variants={container} className="grid gap-6 md:grid-cols-2 lg:grid-cols-7">
        <motion.div variants={item} className="col-span-4">
          <Card className="h-full">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-primary" />
                최근 활동
              </CardTitle>
              <button className="text-xs font-bold text-primary hover:underline">전체보기</button>
            </CardHeader>
            <CardContent>
              <div className="flex flex-col gap-4">
                {[1, 2, 3].map((_, i) => (
                  <div key={i} className="flex items-center gap-4 p-3 rounded-xl bg-accent/30 border border-glass-border">
                    <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                      <Zap className="h-5 w-5 text-primary" />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-sm font-bold">새로운 상품 수집됨</span>
                      <span className="text-xs text-muted-foreground">오너클랜 카테고리 업데이트 완료</span>
                    </div>
                    <span className="ml-auto text-xs font-medium text-muted-foreground">2분 전</span>
                  </div>
                ))}
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
                    <span className="ml-auto px-2 py-0.5 rounded-full bg-primary/20 text-[10px] font-black uppercase text-primary tracking-tighter">Running</span>
                  </div>
                  <div className="text-xs text-muted-foreground font-medium">데이터 SEO 최적화 및 이미지 가공 작업 진행 중 (74%)</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </motion.div>
    </motion.div>
  );
}
