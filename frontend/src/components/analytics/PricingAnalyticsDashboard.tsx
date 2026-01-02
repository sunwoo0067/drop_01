"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
    TrendingUp,
    ArrowUpRight,
    ShieldCheck,
    RefreshCw
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { analyticsClient } from "@/lib/analytics-api";
import type { MarginTrendItem, PricingSimulation, AutomationStats } from "@/lib/types/analytics";

const container = {
    hidden: { opacity: 0 },
    show: {
        opacity: 1,
        transition: {
            staggerChildren: 0.05
        }
    }
};

const item = {
    hidden: { opacity: 0, y: 10 },
    show: { opacity: 1, y: 0 }
};

export default function PricingAnalyticsDashboard() {
    const [trend, setTrend] = useState<MarginTrendItem[]>([]);
    const [simulation, setSimulation] = useState<PricingSimulation | null>(null);
    const [stats, setStats] = useState<AutomationStats | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    const fetchData = useCallback(async () => {
        try {
            setIsLoading(true);
            const [trendData, simData, statsData] = await Promise.all([
                analyticsClient.getMarginTrend(14),
                analyticsClient.getPricingSimulation(),
                analyticsClient.getStats()
            ]);
            setTrend(trendData);
            setSimulation(simData);
            setStats(statsData);
        } catch (error) {
            console.error("Failed to fetch pricing analytics:", error);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    const formatCurrency = (value: number) => {
        return new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW' }).format(value);
    };

    const formatPercent = (value: number) => {
        return `${(value * 100).toFixed(1)}%`;
    };

    if (isLoading || !simulation) {
        return (
            <div className="grid gap-4 grid-cols-1 md:grid-cols-4">
                {[1, 2, 3, 4].map(i => (
                    <Card key={i} className="animate-pulse">
                        <CardContent className="h-24 bg-muted/20" />
                    </Card>
                ))}
            </div>
        );
    }

    // 마진 트렌드 최대값 (차트 높이 계산용)
    const maxMargin = Math.max(...trend.map(t => t.avg_margin), 0.2); // 최소 20% 기준

    return (
        <div className="space-y-4">
            {/* KPI Summary Cards */}
            <motion.div
                variants={container}
                initial="hidden"
                animate="show"
                className="grid gap-3 grid-cols-1 md:grid-cols-4"
            >
                <motion.div variants={item}>
                    <Card className="bg-card border-l-4 border-l-primary">
                        <CardContent className="pt-4 px-4 pb-4">
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] font-medium text-muted-foreground uppercase">대기 중인 가격 권고</span>
                                <Badge variant="outline" className="text-[10px]">{simulation.pending_reco_count}건</Badge>
                            </div>
                            <div className="mt-1 flex items-baseline gap-2">
                                <span className="text-xl font-bold">{simulation.pending_reco_count}</span>
                                <span className="text-[10px] text-muted-foreground">건의 기회</span>
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>

                <motion.div variants={item}>
                    <Card className="bg-card border-l-4 border-l-emerald-500">
                        <CardContent className="pt-4 px-4 pb-4">
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] font-medium text-muted-foreground uppercase">기대 이익 상승분</span>
                                <TrendingUp className="h-3 w-3 text-emerald-500" />
                            </div>
                            <div className="mt-1 flex items-baseline gap-2">
                                <span className="text-xl font-bold text-emerald-600">+{formatCurrency(simulation.expected_lift)}</span>
                            </div>
                            <div className="mt-0.5 flex items-center gap-1">
                                <ArrowUpRight className="h-3 w-3 text-emerald-500" />
                                <span className="text-[10px] font-semibold text-emerald-500">
                                    {simulation.lift_percentage.toFixed(1)}% 수익 개선 기대
                                </span>
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>

                <motion.div variants={item}>
                    <Card className="bg-card border-l-4 border-l-sky-500">
                        <CardContent className="pt-4 px-4 pb-4">
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] font-medium text-muted-foreground uppercase">최근 24시간 집행</span>
                                <motion.div animate={{ scale: [1, 1.1, 1] }} transition={{ repeat: Infinity, duration: 2 }}>
                                    <div className="h-1.5 w-1.5 rounded-full bg-sky-500" />
                                </motion.div>
                            </div>
                            <div className="mt-1 flex items-baseline gap-2">
                                <span className="text-xl font-bold">{stats?.applied_24h || 0}</span>
                                <span className="text-[10px] text-muted-foreground">건 자동 적용됨</span>
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>

            <motion.div variants={item}>
                <Card className="bg-card border-l-4 border-l-amber-500">
                    <CardHeader className="p-0" />
                    <CardContent className="pt-4 px-4 pb-4">
                        <div className="flex items-center justify-between">
                            <span className="text-[10px] font-medium text-muted-foreground uppercase">스로틀링 사용 현황</span>
                            <ShieldCheck className="h-3 w-3 text-amber-500" />
                        </div>
                        <div className="mt-2 space-y-1.5">
                            {stats && Object.values(stats.throttle_status).map((s, idx) => (
                                <div key={idx} className="space-y-0.5">
                                    <div className="flex justify-between text-[8px]">
                                        <span className="truncate max-w-[60px]">{s.name}</span>
                                        <span className={s.usage >= s.limit ? "text-red-500 font-bold" : ""}>
                                            {s.usage}/{s.limit}
                                        </span>
                                    </div>
                                    <div className="h-1 w-full bg-muted/30 rounded-full overflow-hidden">
                                        <div
                                            className={`h-full rounded-full ${s.usage >= s.limit ? 'bg-red-500' : 'bg-amber-500'}`}
                                            style={{ width: `${Math.min((s.usage / s.limit) * 100, 100)}%` }}
                                        />
                                    </div>
                                </div>
                            ))}
                            {!stats && <div className="text-[8px] text-muted-foreground italic">계정 정보 로드 중...</div>}
                        </div>
                    </CardContent>
                </Card>
            </motion.div>
        </motion.div>

            {/* Margin Trend Chart */ }
    <Card className="border border-border bg-card/50">
        <CardHeader className="flex flex-row items-center justify-between py-3 px-4 h-12">
            <CardTitle className="text-xs font-semibold flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-primary" />
                일자별 평균 마진율 추이 (최근 14일)
            </CardTitle>
            <Button variant="ghost" size="xs" onClick={fetchData}>
                <RefreshCw className="h-3 w-3 mr-1" />
                새로고침
            </Button>
        </CardHeader>
        <CardContent className="px-4 pb-4 pt-2">
            <div className="h-48 flex items-end gap-1.5 pt-6 relative">
                {/* Grid Lines */}
                <div className="absolute inset-0 flex flex-col justify-between border-b border-l border-muted/30">
                    {[0.2, 0.15, 0.1, 0.05, 0].map(val => (
                        <div key={val} className="w-full border-t border-muted/10 relative">
                            <span className="absolute -left-6 -top-1.5 text-[8px] text-muted-foreground">
                                {(val * 100).toFixed(0)}%
                            </span>
                        </div>
                    ))}
                </div>

                {/* Bars */}
                {trend.length > 0 ? trend.map((p, i) => {
                    const height = (p.avg_margin / maxMargin) * 100;

                    return (
                        <div key={i} className="flex-1 flex flex-col items-center group relative h-full justify-end">
                            <motion.div
                                initial={{ height: 0 }}
                                animate={{ height: `${Math.max(Math.abs(height), 2)}%` }}
                                className={`w-full rounded-t-sm transition-all ${p.avg_margin >= 0.1 ? 'bg-emerald-500/60 group-hover:bg-emerald-500' :
                                    p.avg_margin > 0 ? 'bg-amber-500/60 group-hover:bg-amber-500' :
                                        'bg-red-500/60 group-hover:bg-red-500'
                                    }`}
                            />
                            {/* Tooltip (simplified) */}
                            <div className="absolute -top-6 left-1/2 -translate-x-1/2 bg-popover text-popover-foreground text-[8px] px-1 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity z-10 whitespace-nowrap shadow-sm border border-border">
                                {formatPercent(p.avg_margin)} ({p.order_count}건)
                            </div>
                            <span className="text-[8px] text-muted-foreground mt-2 rotate-[-45deg] origin-top-left whitespace-nowrap">
                                {p.date.split('-').slice(1).join('/')}
                            </span>
                        </div>
                    );
                }) : (
                    <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
                        분석 데이터가 부족합니다.
                    </div>
                )}
            </div>
        </CardContent>
    </Card>
        </div >
    );
}
