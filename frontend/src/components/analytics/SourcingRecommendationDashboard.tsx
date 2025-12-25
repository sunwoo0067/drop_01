"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Lightbulb, AlertTriangle, TrendingUp, CheckCircle, XCircle, RefreshCw, Hourglass } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { recommendationsAPI } from "@/lib/analytics-api";
import type { SourcingRecommendation, RecommendationSummary, ReorderAlert } from "@/lib/types/analytics";

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

export default function SourcingRecommendationDashboard() {
    const [pendingRecommendations, setPendingRecommendations] = useState<SourcingRecommendation[]>([]);
    const [summary, setSummary] = useState<RecommendationSummary | null>(null);
    const [reorderAlerts, setReorderAlerts] = useState<ReorderAlert[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    const fetchData = async () => {
        try {
            setIsLoading(true);
            const [pendingData, summaryData, alertsData] = await Promise.all([
                recommendationsAPI.getPending(10),
                recommendationsAPI.getSummary(7),
                recommendationsAPI.getReorderAlerts(),
            ]);
            setPendingRecommendations(pendingData);
            setSummary(summaryData);
            setReorderAlerts(alertsData.alerts || []);
        } catch (error) {
            console.error("Failed to fetch recommendation data:", error);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const formatCurrency = (value: number) => {
        return new Intl.NumberFormat("ko-KR", {
            style: "currency",
            currency: "KRW",
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        }).format(value);
    };

    const getScoreColor = (score: number) => {
        if (score >= 80) return "text-emerald-500 bg-emerald-500/10";
        if (score >= 60) return "text-amber-500 bg-amber-500/10";
        return "text-red-500 bg-red-500/10";
    };

    const handleAccept = async (recommendationId: string) => {
        try {
            await recommendationsAPI.acceptRecommendation(recommendationId, {
                action_taken: "ORDER_PLACED",
            });
            fetchData();
        } catch (error) {
            console.error("Failed to accept recommendation:", error);
        }
    };

    const handleReject = async (recommendationId: string) => {
        try {
            await recommendationsAPI.rejectRecommendation(recommendationId, {
                action_taken: "REJECTED",
            });
            fetchData();
        } catch (error) {
            console.error("Failed to reject recommendation:", error);
        }
    };

    if (isLoading) {
        return (
            <div className="grid gap-6 md:grid-cols-2">
                <Card>
                    <CardHeader>
                        <CardTitle>대기 중 추천</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-3">
                            {[...Array(3)].map((_, i) => (
                                <div key={i} className="animate-pulse h-20 bg-muted rounded-lg" />
                            ))}
                        </div>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader>
                        <CardTitle>재고 부족 알림</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-3">
                            {[...Array(3)].map((_, i) => (
                                <div key={i} className="animate-pulse h-20 bg-muted rounded-lg" />
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Summary Cards */}
            {summary && (
                <div className="grid gap-4 md:grid-cols-4">
                    <Card className="bg-gradient-to-br from-primary/5 to-transparent border-primary/20">
                        <CardContent className="p-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <div className="text-xs text-muted-foreground font-bold uppercase tracking-wider">
                                        총 추천
                                    </div>
                                    <div className="text-2xl font-black mt-1">
                                        {summary.total_recommendations}
                                    </div>
                                </div>
                                <Lightbulb className="h-8 w-8 text-primary/50" />
                            </div>
                        </CardContent>
                    </Card>

                    <Card className="bg-gradient-to-br from-amber-500/5 to-transparent border-amber-500/20">
                        <CardContent className="p-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <div className="text-xs text-muted-foreground font-bold uppercase tracking-wider">
                                        대기 중
                                    </div>
                                    <div className="text-2xl font-black mt-1 text-amber-500">
                                        {summary.pending}
                                    </div>
                                </div>
                                <Hourglass className="h-8 w-8 text-amber-500/50" />
                            </div>
                        </CardContent>
                    </Card>

                    <Card className="bg-gradient-to-br from-emerald-500/5 to-transparent border-emerald-500/20">
                        <CardContent className="p-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <div className="text-xs text-muted-foreground font-bold uppercase tracking-wider">
                                        수락률
                                    </div>
                                    <div className="text-2xl font-black mt-1 text-emerald-500">
                                        {(summary.acceptance_rate * 100).toFixed(1)}%
                                    </div>
                                </div>
                                <CheckCircle className="h-8 w-8 text-emerald-500/50" />
                            </div>
                        </CardContent>
                    </Card>

                    <Card className="bg-gradient-to-br from-blue-500/5 to-transparent border-blue-500/20">
                        <CardContent className="p-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <div className="text-xs text-muted-foreground font-bold uppercase tracking-wider">
                                        평균 점수
                                    </div>
                                    <div className="text-2xl font-black mt-1 text-blue-500">
                                        {summary.avg_overall_score.toFixed(1)}
                                    </div>
                                </div>
                                <TrendingUp className="h-8 w-8 text-blue-500/50" />
                            </div>
                        </CardContent>
                    </Card>
                </div>
            )}

            {/* Main Content */}
            <div className="grid gap-6 md:grid-cols-2">
                {/* Pending Recommendations */}
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between">
                        <CardTitle className="flex items-center gap-2">
                            <Lightbulb className="h-5 w-5 text-amber-500" />
                            대기 중 추천
                        </CardTitle>
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={fetchData}
                            className="text-xs"
                        >
                            <RefreshCw className="h-4 w-4" />
                        </Button>
                    </CardHeader>
                    <CardContent>
                        {pendingRecommendations.length === 0 ? (
                            <div className="text-center py-8 text-sm text-muted-foreground">
                                대기 중인 추천이 없습니다.
                            </div>
                        ) : (
                            <motion.div
                                variants={container}
                                initial="hidden"
                                animate="show"
                                className="space-y-3"
                            >
                                {pendingRecommendations.map((rec) => (
                                    <motion.div
                                        key={rec.id}
                                        variants={item}
                                        className="p-4 rounded-xl bg-accent/30 border border-border hover:border-primary/50 transition-colors"
                                    >
                                        <div className="flex items-start justify-between gap-4">
                                            <div className="flex-1 min-w-0">
                                                <div className="font-semibold text-sm mb-1">
                                                    {rec.product_name || "Unknown Product"}
                                                </div>
                                                <div className="text-xs text-muted-foreground mb-2">
                                                    {rec.recommendation_type} · {rec.recommended_quantity}개
                                                </div>
                                                <div className="flex items-center gap-2 text-xs">
                                                    <div className={`px-2 py-0.5 rounded-full font-bold ${getScoreColor(rec.overall_score)}`}>
                                                        {rec.overall_score.toFixed(0)}점
                                                    </div>
                                                    <span className="text-muted-foreground">
                                                        예상 이익: {formatCurrency(rec.expected_margin)}
                                                    </span>
                                                </div>
                                            </div>
                                            <div className="flex gap-2 shrink-0">
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => handleReject(rec.id)}
                                                    className="h-8 w-8 p-0 text-red-500 hover:text-red-600 hover:bg-red-500/10"
                                                >
                                                    <XCircle className="h-4 w-4" />
                                                </Button>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => handleAccept(rec.id)}
                                                    className="h-8 w-8 p-0 text-emerald-500 hover:text-emerald-600 hover:bg-emerald-500/10"
                                                >
                                                    <CheckCircle className="h-4 w-4" />
                                                </Button>
                                            </div>
                                        </div>
                                    </motion.div>
                                ))}
                            </motion.div>
                        )}
                    </CardContent>
                </Card>

                {/* Reorder Alerts */}
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between">
                        <CardTitle className="flex items-center gap-2">
                            <AlertTriangle className="h-5 w-5 text-red-500" />
                            재고 부족 알림
                        </CardTitle>
                        <div className="text-xs text-muted-foreground">
                            {reorderAlerts.length}개 알림
                        </div>
                    </CardHeader>
                    <CardContent>
                        {reorderAlerts.length === 0 ? (
                            <div className="text-center py-8 text-sm text-muted-foreground">
                                재고 부족 알림이 없습니다.
                            </div>
                        ) : (
                            <motion.div
                                variants={container}
                                initial="hidden"
                                animate="show"
                                className="space-y-3"
                            >
                                {reorderAlerts.map((alert) => (
                                    <motion.div
                                        key={alert.recommendation_id}
                                        variants={item}
                                        className="p-4 rounded-xl bg-red-500/5 border border-red-500/20"
                                    >
                                        <div className="flex items-start justify-between gap-4">
                                            <div className="flex-1 min-w-0">
                                                <div className="font-semibold text-sm mb-1 text-red-900 dark:text-red-100">
                                                    {alert.product_name}
                                                </div>
                                                <div className="text-xs text-red-700 dark:text-red-300 mb-2">
                                                    재고가 {alert.stock_days_left}일 남았습니다.
                                                </div>
                                                <div className="flex items-center gap-2 text-xs">
                                                    <span className="text-muted-foreground">
                                                        추천 수량: {alert.recommended_quantity}개
                                                    </span>
                                                    <span className={`px-2 py-0.5 rounded-full font-bold ${getScoreColor(alert.overall_score)}`}>
                                                        {alert.overall_score.toFixed(0)}점
                                                    </span>
                                                </div>
                                            </div>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => handleAccept(alert.recommendation_id)}
                                                className="shrink-0 bg-red-500/10 hover:bg-red-500/20 text-red-700 hover:text-red-800 dark:text-red-200 dark:hover:text-red-100 border-red-500/30"
                                            >
                                                즉시 주문
                                            </Button>
                                        </div>
                                    </motion.div>
                                ))}
                            </motion.div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
