"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { DollarSign, ShoppingCart, TrendingUp, Activity } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { analyticsAPI } from "@/lib/analytics-api";
import type { SalesSummary } from "@/lib/types/analytics";

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

export default function SalesSummaryCards() {
    const [summary, setSummary] = useState<SalesSummary | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [periodType, setPeriodType] = useState<"weekly" | "monthly">("weekly");

    const fetchSummary = async () => {
        try {
            setIsLoading(true);
            const data = await analyticsAPI.getSummary(periodType);
            setSummary(data);
        } catch (error) {
            console.error("Failed to fetch sales summary:", error);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchSummary();
    }, [periodType]);

    const formatCurrency = (value: number) => {
        return new Intl.NumberFormat("ko-KR", {
            style: "currency",
            currency: "KRW",
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        }).format(value);
    };

    const formatPercent = (value: number) => {
        return `${(value * 100).toFixed(1)}%`;
    };

    const getGrowthColor = (value: number) => {
        if (value > 0) return "text-emerald-500";
        if (value < 0) return "text-red-500";
        return "text-muted-foreground";
    };

    const getGrowthIcon = (value: number) => {
        if (value > 0) return <TrendingUp className="h-4 w-4" />;
        if (value < 0) return <TrendingUp className="h-4 w-4 rotate-180" />;
        return <Activity className="h-4 w-4" />;
    };

    if (isLoading || !summary) {
        return (
            <div className="grid gap-6 md:grid-cols-4">
                {[...Array(4)].map((_, i) => (
                    <Card key={i} className="animate-pulse">
                        <CardHeader className="pb-2">
                            <div className="h-4 w-32 bg-muted rounded" />
                        </CardHeader>
                        <CardContent>
                            <div className="h-10 w-24 bg-muted rounded mb-2" />
                            <div className="h-2 w-full bg-muted rounded" />
                        </CardContent>
                    </Card>
                ))}
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Period Selector */}
            <div className="flex items-center justify-end gap-2">
                <button
                    onClick={() => setPeriodType("weekly")}
                    className={`px-3 py-1.5 rounded-lg text-sm font-semibold transition-all ${periodType === "weekly"
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground hover:bg-accent"
                        }`}
                >
                    주간
                </button>
                <button
                    onClick={() => setPeriodType("monthly")}
                    className={`px-3 py-1.5 rounded-lg text-sm font-semibold transition-all ${periodType === "monthly"
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground hover:bg-accent"
                        }`}
                >
                    월간
                </button>
            </div>

            {/* Summary Cards */}
            <motion.div
                variants={container}
                initial="hidden"
                animate="show"
                className="grid gap-6 md:grid-cols-4"
            >
                {/* Total Revenue */}
                <motion.div variants={item}>
                    <Card className="overflow-hidden group">
                        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                            <DollarSign className="h-24 w-24" />
                        </div>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-bold uppercase tracking-widest text-muted-foreground">
                                총 매출
                            </CardTitle>
                            <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center">
                                <DollarSign className="h-4 w-4 text-primary" />
                            </div>
                        </CardHeader>
                        <CardContent>
                            <div className="text-4xl font-black">{formatCurrency(summary.total_revenue)}</div>
                            <div className="mt-2 flex items-center gap-2">
                                <div className={`flex items-center gap-1 text-sm font-bold ${getGrowthColor(summary.avg_growth_rate)}`}>
                                    {getGrowthIcon(summary.avg_growth_rate)}
                                    <span>{formatPercent(summary.avg_growth_rate)}</span>
                                </div>
                                <span className="text-xs text-muted-foreground">전 대비</span>
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>

                {/* Total Orders */}
                <motion.div variants={item}>
                    <Card className="overflow-hidden group">
                        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                            <ShoppingCart className="h-24 w-24" />
                        </div>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-bold uppercase tracking-widest text-muted-foreground">
                                총 주문
                            </CardTitle>
                            <div className="h-8 w-8 rounded-lg bg-blue-500/10 flex items-center justify-center">
                                <ShoppingCart className="h-4 w-4 text-blue-500" />
                            </div>
                        </CardHeader>
                        <CardContent>
                            <div className="text-4xl font-black">{summary.total_orders.toLocaleString()}</div>
                            <div className="mt-2 text-xs font-bold text-muted-foreground">
                                {periodType === "weekly" ? "지난 7일간" : "지난 30일간"}
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>

                {/* Total Profit */}
                <motion.div variants={item}>
                    <Card className="overflow-hidden group">
                        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                            <TrendingUp className="h-24 w-24" />
                        </div>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-bold uppercase tracking-widest text-muted-foreground">
                                정밀 순이익
                            </CardTitle>
                            <div className="h-8 w-8 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                                <TrendingUp className="h-4 w-4 text-emerald-500" />
                            </div>
                        </CardHeader>
                        <CardContent>
                            <div className="text-4xl font-black text-emerald-500">
                                {formatCurrency(summary.total_profit)}
                            </div>
                            <div className="mt-2 text-[10px] font-bold text-muted-foreground flex flex-col gap-1">
                                <div className="flex justify-between">
                                    <span>마켓 수수료:</span>
                                    <span className="text-red-400">-{formatCurrency(summary.actual_fees || 0)}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span>예상 부가세:</span>
                                    <span className="text-amber-400">-{formatCurrency(summary.actual_vat || 0)}</span>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>

                {/* Net Settlement */}
                <motion.div variants={item}>
                    <Card className="overflow-hidden group bg-gradient-to-br from-primary/5 to-transparent border-primary/20">
                        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                            <Activity className="h-24 w-24" />
                        </div>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-bold uppercase tracking-widest text-primary">
                                정산 예정액
                            </CardTitle>
                            <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center">
                                <Activity className="h-4 w-4 text-primary" />
                            </div>
                        </CardHeader>
                        <CardContent>
                            <div className="text-4xl font-black text-primary">
                                {formatCurrency(summary.net_settlement || 0)}
                            </div>
                            <div className="mt-2 text-xs font-bold text-muted-foreground">
                                평균 이익률: {formatPercent(summary.avg_margin_rate)}
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>
            </motion.div>
        </div>
    );
}
