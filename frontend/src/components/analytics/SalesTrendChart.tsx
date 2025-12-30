"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { BarChart3, RefreshCw, TrendingUp, TrendingDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { analyticsAPI } from "@/lib/analytics-api";
import type { SalesTrend, SalesTrendDataPoint } from "@/lib/types/analytics";

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

interface SalesTrendChartProps {
    periodType?: "weekly" | "monthly";
    periods?: number;
}

export default function SalesTrendChart({ periodType = "weekly", periods = 12 }: SalesTrendChartProps) {
    const [trend, setTrend] = useState<SalesTrend | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [showPrediction, setShowPrediction] = useState(true);

    const fetchTrend = useCallback(async () => {
        try {
            setIsLoading(true);
            const data = await analyticsAPI.getTrend(periodType, periods);
            setTrend(data);
        } catch (error) {
            console.error("Failed to fetch sales trend:", error);
        } finally {
            setIsLoading(false);
        }
    }, [periodType, periods]);

    useEffect(() => {
        fetchTrend();
    }, [fetchTrend]);

    const formatCompactCurrency = (value: number) => {
        if (value >= 100000000) {
            return `${(value / 100000000).toFixed(1)}억`;
        } else if (value >= 10000) {
            return `${(value / 10000).toFixed(1)}만`;
        }
        return value.toLocaleString();
    };

    const getGrowthColor = (current: number, previous: number) => {
        if (previous === 0) return "text-muted-foreground";
        const growth = (current - previous) / previous;
        if (growth > 0) return "text-emerald-500";
        if (growth < 0) return "text-red-500";
        return "text-muted-foreground";
    };

    const getGrowthPercent = (current: number, previous: number) => {
        if (previous === 0) return "0.0%";
        const growth = ((current - previous) / previous) * 100;
        return `${growth > 0 ? "+" : ""}${growth.toFixed(1)}%`;
    };

    const getGrowthIcon = (current: number, previous: number) => {
        if (previous === 0) return null;
        const growth = (current - previous) / previous;
        if (growth > 0) return <TrendingUp className="h-3 w-3" />;
        if (growth < 0) return <TrendingDown className="h-3 w-3" />;
        return null;
    };

    if (isLoading || !trend) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <BarChart3 className="h-5 w-5 text-primary" />
                        매출 추이
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="h-[300px] animate-pulse bg-muted rounded-lg" />
                </CardContent>
            </Card>
        );
    }

    // Find max revenue for bar height calculation
    const maxRevenue = Math.max(...trend.data_points.map(p => p.total_revenue));

    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5 text-primary" />
                    매출 추이
                </CardTitle>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowPrediction(!showPrediction)}
                        className="text-xs"
                    >
                        {showPrediction ? "예측 숨기기" : "예측 보기"}
                    </Button>
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={fetchTrend}
                        className="text-xs"
                    >
                        <RefreshCw className="h-4 w-4" />
                    </Button>
                </div>
            </CardHeader>
            <CardContent>
                <motion.div
                    variants={container}
                    initial="hidden"
                    animate="show"
                    className="space-y-4"
                >
                    {/* Chart Legend */}
                    <div className="flex items-center gap-4 text-xs">
                        <div className="flex items-center gap-2">
                            <div className="w-3 h-3 rounded bg-blue-500" />
                            <span className="text-muted-foreground">실제 매출</span>
                        </div>
                        {showPrediction && (
                            <div className="flex items-center gap-2">
                                <div className="w-3 h-3 rounded bg-emerald-500 border-2 border-dashed border-emerald-600" />
                                <span className="text-muted-foreground">예측 매출</span>
                            </div>
                        )}
                    </div>

                    {/* Trend Bars */}
                    <div className="space-y-2">
                        {trend.data_points.map((point: SalesTrendDataPoint, index: number) => {
                            const previousPoint = index > 0 ? trend.data_points[index - 1] : null;
                            const heightPercent = (point.total_revenue / maxRevenue) * 100;

                            return (
                                <motion.div
                                    key={index}
                                    variants={item}
                                    className="flex items-center gap-4 group"
                                >
                                    {/* Period Label */}
                                    <div className="w-24 text-xs text-muted-foreground text-right shrink-0">
                                        {point.period}
                                    </div>

                                    {/* Bar Container */}
                                    <div className="flex-1 flex items-center gap-2 min-w-0">
                                        {/* Actual Revenue Bar */}
                                        <div className="flex-1 h-8 bg-muted rounded-lg overflow-hidden relative">
                                            <motion.div
                                                initial={{ width: 0 }}
                                                animate={{ width: `${heightPercent}%` }}
                                                transition={{ duration: 0.5, delay: index * 0.05 }}
                                                className="h-full bg-blue-500 rounded-lg"
                                            />
                                            <div className="absolute inset-0 flex items-center justify-center text-xs font-bold text-white drop-shadow">
                                                {formatCompactCurrency(point.total_revenue)}
                                            </div>
                                        </div>

                                        {/* Prediction Bar */}
                                        {showPrediction && point.predicted_revenue && (
                                            <div className="w-24 h-8 bg-muted rounded-lg overflow-hidden relative border-2 border-dashed border-emerald-600">
                                                <motion.div
                                                    initial={{ width: 0 }}
                                                    animate={{ width: `${(point.predicted_revenue / maxRevenue) * 100}%` }}
                                                    transition={{ duration: 0.5, delay: index * 0.05 + 0.2 }}
                                                    className="h-full bg-emerald-500/50 rounded-lg"
                                                />
                                                <div className="absolute inset-0 flex items-center justify-center text-xs font-bold text-emerald-700 drop-shadow">
                                                    {formatCompactCurrency(point.predicted_revenue)}
                                                </div>
                                            </div>
                                        )}
                                    </div>

                                    {/* Growth Indicator */}
                                    {previousPoint && (
                                        <div className={`flex items-center gap-1 text-xs font-bold ${getGrowthColor(point.total_revenue, previousPoint.total_revenue)} w-20 shrink-0`}>
                                            {getGrowthIcon(point.total_revenue, previousPoint.total_revenue)}
                                            <span>{getGrowthPercent(point.total_revenue, previousPoint.total_revenue)}</span>
                                        </div>
                                    )}
                                </motion.div>
                            );
                        })}
                    </div>
                </motion.div>
            </CardContent>
        </Card>
    );
}
