"use client";

import { useEffect, useState } from "react";
import { ShoppingCart, TrendingUp, Activity } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { analyticsAPI } from "@/lib/analytics-api";
import type { SalesSummary } from "@/lib/types/analytics";

export default function SalesSummaryCards() {
    const [summary, setSummary] = useState<SalesSummary | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [periodType, setPeriodType] = useState<"weekly" | "monthly">("weekly");

    useEffect(() => {
        const fetchSummary = async () => {
            try {
                setIsLoading(true);
                const data = await analyticsAPI.getSummary(periodType);
                setSummary(data);
            } catch (error) {
                console.error("Failed to fetch sales summary", error);
            } finally {
                setIsLoading(false);
            }
        };
        fetchSummary();
    }, [periodType]);

    const getGrowthIcon = (rate: number) => {
        if (rate > 0) return <TrendingUp className="h-3 w-3" />;
        if (rate < 0) return <TrendingUp className="h-3 w-3 rotate-180" />;
        return <Activity className="h-3 w-3" />;
    };

    const getGrowthColor = (rate: number) => {
        if (rate > 0) return "text-success";
        if (rate < 0) return "text-destructive";
        return "text-foreground";
    };

    const formatCurrency = (value: number) => {
        return new Intl.NumberFormat('ko-KR', {
            style: 'currency',
            currency: 'KRW',
            maximumFractionDigits: 0
        }).format(value);
    };

    const formatPercent = (value: number) => {
        return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;
    };

    if (isLoading || !summary) {
        return (
            <Card className="border border-border">
                <CardHeader className="pb-2">
                    <CardTitle className="text-xs">매출 요약</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid gap-3 grid-cols-4">
                        {[...Array(4)].map((_, i) => (
                            <div key={i} className="space-y-2">
                                <div className="h-4 w-16 bg-muted rounded-sm animate-pulse" />
                                <div className="h-8 w-20 bg-muted rounded-sm mb-1 animate-pulse" />
                                <div className="h-2 w-full bg-muted rounded-sm animate-pulse" />
                            </div>
                        ))}
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-3">
            {/* Period Selector */}
            <div className="flex items-center justify-end gap-2 px-4 py-2 border-b border-border bg-card">
                <Button
                    variant={periodType === "weekly" ? "primary" : "ghost"}
                    size="xs"
                    onClick={() => setPeriodType("weekly")}
                >
                    주간
                </Button>
                <Button
                    variant={periodType === "monthly" ? "primary" : "ghost"}
                    size="xs"
                    onClick={() => setPeriodType("monthly")}
                >
                    월간
                </Button>
            </div>

            {/* Summary Cards */}
            <div className="grid gap-3 grid-cols-4">
                {/* Total Revenue */}
                <div className="border border-border rounded-sm bg-card">
                    <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                        <CardTitle className="text-[10px] uppercase text-muted-foreground">
                            총 매출
                        </CardTitle>
                        <div className="h-6 w-6 rounded-sm bg-primary/10 flex items-center justify-center">
                            <ShoppingCart className="h-3 w-3 text-primary" />
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="text-xl font-bold text-foreground">{formatCurrency(summary.total_revenue)}</div>
                        <div className="mt-2 flex items-center gap-1">
                            <div className={`flex items-center gap-0.5 text-[11px] font-medium ${getGrowthColor(summary.avg_growth_rate)}`}>
                                {getGrowthIcon(summary.avg_growth_rate)}
                                <span>{formatPercent(summary.avg_growth_rate)}</span>
                            </div>
                            <span className="text-[10px] text-muted-foreground">전 대비</span>
                        </div>
                    </CardContent>
                </div>

                {/* Total Orders */}
                <div className="border border-border rounded-sm bg-card">
                    <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                        <CardTitle className="text-[10px] uppercase text-muted-foreground">
                            총 주문
                        </CardTitle>
                        <div className="h-6 w-6 rounded-sm bg-info/10 flex items-center justify-center">
                            <ShoppingCart className="h-3 w-3 text-info" />
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="text-xl font-bold text-foreground">{summary.total_orders.toLocaleString()}</div>
                        <div className="mt-1 text-[10px] font-medium text-muted-foreground">
                            {periodType === "weekly" ? "지난 7일간" : "지난 30일간"}
                        </div>
                    </CardContent>
                </div>

                {/* Total Profit */}
                <div className="border border-border rounded-sm bg-card">
                    <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                        <CardTitle className="text-[10px] uppercase text-muted-foreground">
                            순이익
                        </CardTitle>
                        <div className="h-6 w-6 rounded-sm bg-success/10 flex items-center justify-center">
                            <TrendingUp className="h-3 w-3 text-success" />
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="text-xl font-bold text-success">{formatCurrency(summary.total_profit)}</div>
                        <div className="mt-2 space-y-1 text-[10px]">
                            <div className="flex justify-between">
                                <span className="text-muted-foreground">마켓 수수료:</span>
                                <span className="text-destructive font-medium">-{formatCurrency(summary.actual_fees || 0)}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-muted-foreground">예상 부가세:</span>
                                <span className="text-warning font-medium">-{formatCurrency(summary.actual_vat || 0)}</span>
                            </div>
                        </div>
                    </CardContent>
                </div>

                {/* Net Settlement */}
                <div className="border border-border rounded-sm bg-card">
                    <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                        <CardTitle className="text-[10px] uppercase text-muted-foreground">
                            정산 예상액
                        </CardTitle>
                        <div className="h-6 w-6 rounded-sm bg-primary/10 flex items-center justify-center">
                            <Activity className="h-3 w-3 text-primary" />
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="text-xl font-bold text-primary">{formatCurrency(summary.net_settlement || 0)}</div>
                        <div className="mt-2 text-[10px] text-muted-foreground italic">
                            최종 정산 금액
                        </div>
                    </CardContent>
                </div>
            </div>
        </div>
    );
}
