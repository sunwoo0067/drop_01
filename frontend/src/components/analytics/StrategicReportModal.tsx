"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
    X,
    Brain,
    TrendingUp,
    AlertTriangle,
    Target,
    Zap,
    ChevronRight,
    Loader2,
    ShieldAlert,
    Lightbulb,
    BarChart
} from "lucide-react";
import { analyticsAPI } from "@/lib/analytics-api";
import type { StrategicReport, OptimalPricePrediction } from "@/lib/types/analytics";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { badgeVariants } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

interface StrategicReportModalProps {
    productId: string;
    productName: string;
    onClose: () => void;
}

export default function StrategicReportModal({ productId, productName, onClose }: StrategicReportModalProps) {
    const [report, setReport] = useState<StrategicReport | null>(null);
    const [prediction, setPrediction] = useState<OptimalPricePrediction | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isUpdating, setIsUpdating] = useState(false);
    const [updateStatus, setUpdateStatus] = useState<{ type: 'success' | 'error', message: string } | null>(null);

    useEffect(() => {
        const fetchData = async () => {
            try {
                setIsLoading(true);
                const [reportData, predictionData] = await Promise.all([
                    analyticsAPI.getStrategicReport(productId),
                    analyticsAPI.getOptimalPricePrediction(productId)
                ]);
                setReport(reportData);
                setPrediction(predictionData);
            } catch (error) {
                console.error("Failed to fetch strategic data:", error);
            } finally {
                setIsLoading(false);
            }
        };

        fetchData();
    }, [productId]);

    const handleApplyPrice = async () => {
        if (!prediction || !prediction.market_code || !prediction.account_id || !prediction.market_item_id) {
            setUpdateStatus({ type: 'error', message: '마켓 연동 정보가 부족하여 가격을 수정할 수 없습니다.' });
            return;
        }

        try {
            setIsUpdating(true);
            setUpdateStatus(null);

            const result = await analyticsAPI.updatePrice({
                market_code: prediction.market_code,
                account_id: prediction.account_id,
                market_item_id: prediction.market_item_id,
                price: prediction.optimal_price
            });

            if (result.success) {
                setUpdateStatus({ type: 'success', message: '마켓 판매가가 성공적으로 변경되었습니다.' });
            } else {
                setUpdateStatus({ type: 'error', message: result.message || '가격 수정 요청 중 오류가 발생했습니다.' });
            }
        } catch (error) {
            console.error("Price update failed:", error);
            setUpdateStatus({ type: 'error', message: '서버 통신 중 오류가 발생했습니다.' });
        } finally {
            setIsUpdating(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
            <motion.div
                initial={{ opacity: 0, scale: 0.9, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9, y: 20 }}
                className="relative w-full max-w-4xl max-h-[90vh] overflow-hidden bg-card border rounded-3xl shadow-2xl flex flex-col"
            >
                {/* Header */}
                <div className="p-6 border-b flex items-center justify-between bg-gradient-to-r from-primary/5 via-transparent to-primary/5">
                    <div className="flex items-center gap-4">
                        <div className="h-12 w-12 rounded-2xl bg-primary/10 flex items-center justify-center">
                            <Brain className="h-6 w-6 text-primary" />
                        </div>
                        <div>
                            <h2 className="text-xl font-black tracking-tight">{productName}</h2>
                            <p className="text-sm text-muted-foreground font-medium">AI 전략 분석 보고서</p>
                        </div>
                    </div>
                    <Button variant="ghost" size="icon" onClick={onClose} className="rounded-full">
                        <X className="h-5 w-5" />
                    </Button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
                    {isLoading ? (
                        <div className="h-64 flex flex-col items-center justify-center gap-4">
                            <Loader2 className="h-12 w-12 text-primary animate-spin" />
                            <p className="text-muted-foreground animate-pulse font-bold">
                                AI가 판매 데이터를 분석하여 전략을 수립 중입니다...
                            </p>
                        </div>
                    ) : report ? (
                        <div className="space-y-8">
                            {/* Market Position */}
                            <section className="relative overflow-hidden p-6 rounded-2xl bg-accent/30 border border-primary/10">
                                <div className="absolute top-0 right-0 p-8 opacity-5">
                                    <Target className="h-32 w-32" />
                                </div>
                                <h3 className="text-sm font-bold text-primary uppercase tracking-widest mb-2 flex items-center gap-2">
                                    <Target className="h-4 w-4" /> Market Position
                                </h3>
                                <p className="text-2xl font-black text-foreground">
                                    {report.market_position}
                                </p>
                            </section>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                {/* SWOT Analysis */}
                                <Card className="border-none bg-accent/20">
                                    <CardContent className="p-6">
                                        <h3 className="text-sm font-bold text-muted-foreground uppercase tracking-widest mb-4 flex items-center gap-2">
                                            <BarChart className="h-4 w-4" /> SWOT 분석
                                        </h3>
                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="space-y-2">
                                                <span className="text-[10px] font-black text-emerald-500 uppercase tracking-tighter">Strengths</span>
                                                <ul className="text-xs space-y-1">
                                                    {report.swot_analysis.strengths.map((s, i) => (
                                                        <li key={i} className="flex gap-2"><ChevronRight className="h-3 w-3 shrink-0 mt-0.5" />{s}</li>
                                                    ))}
                                                </ul>
                                            </div>
                                            <div className="space-y-2">
                                                <span className="text-[10px] font-black text-amber-500 uppercase tracking-tighter">Weaknesses</span>
                                                <ul className="text-xs space-y-1">
                                                    {report.swot_analysis.weaknesses.map((w, i) => (
                                                        <li key={i} className="flex gap-2"><ChevronRight className="h-3 w-3 shrink-0 mt-0.5" />{w}</li>
                                                    ))}
                                                </ul>
                                            </div>
                                            <div className="space-y-2 mt-2">
                                                <span className="text-[10px] font-black text-blue-500 uppercase tracking-tighter">Opportunities</span>
                                                <ul className="text-xs space-y-1">
                                                    {report.swot_analysis.opportunities.map((o, i) => (
                                                        <li key={i} className="flex gap-2"><ChevronRight className="h-3 w-3 shrink-0 mt-0.5" />{o}</li>
                                                    ))}
                                                </ul>
                                            </div>
                                            <div className="space-y-2 mt-2">
                                                <span className="text-[10px] font-black text-red-500 uppercase tracking-tighter">Threats</span>
                                                <ul className="text-xs space-y-1">
                                                    {report.swot_analysis.threats.map((t, i) => (
                                                        <li key={i} className="flex gap-2"><ChevronRight className="h-3 w-3 shrink-0 mt-0.5" />{t}</li>
                                                    ))}
                                                </ul>
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>

                                {/* Pricing Strategy */}
                                <Card className="border-none bg-primary/5">
                                    <CardContent className="p-6">
                                        <div className="flex items-center justify-between mb-4">
                                            <h3 className="text-sm font-bold text-primary uppercase tracking-widest flex items-center gap-2">
                                                <TrendingUp className="h-4 w-4" /> 가격 전략
                                            </h3>
                                            {prediction && (
                                                <div className={cn(
                                                    "px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-tighter",
                                                    prediction.strategy === 'Premium' ? "bg-purple-500 text-white" :
                                                        prediction.strategy === 'Clearance' ? "bg-red-500 text-white" :
                                                            "bg-blue-500 text-white"
                                                )}>
                                                    {prediction.strategy}
                                                </div>
                                            )}
                                        </div>

                                        {prediction ? (
                                            <div className="space-y-4">
                                                <div className="p-4 rounded-xl bg-background/50 border border-primary/10">
                                                    <div className="flex items-baseline justify-between mb-2">
                                                        <span className="text-xs text-muted-foreground font-bold italic">AI 추천가</span>
                                                        <span className="text-2xl font-black text-primary">
                                                            {prediction.optimal_price.toLocaleString()}원
                                                        </span>
                                                    </div>
                                                    <p className="text-xs font-medium text-muted-foreground leading-relaxed">
                                                        {prediction.reason}
                                                    </p>
                                                </div>

                                                <div className="flex items-center gap-2">
                                                    <Button
                                                        onClick={handleApplyPrice}
                                                        disabled={isUpdating || !prediction.market_item_id}
                                                        size="sm"
                                                        className="w-full rounded-xl font-black gap-2 h-10 shadow-lg shadow-primary/20"
                                                    >
                                                        {isUpdating ? (
                                                            <Loader2 className="h-4 w-4 animate-spin" />
                                                        ) : (
                                                            <Zap className="h-4 w-4 fill-current" />
                                                        )}
                                                        AI 추천가 마켓 반영
                                                    </Button>
                                                </div>

                                                {updateStatus && (
                                                    <motion.div
                                                        initial={{ opacity: 0, y: -5 }}
                                                        animate={{ opacity: 1, y: 0 }}
                                                        className={cn(
                                                            "p-2 rounded-lg text-[10px] font-bold text-center",
                                                            updateStatus.type === 'success' ? "bg-emerald-500/10 text-emerald-600" : "bg-red-500/10 text-red-600"
                                                        )}
                                                    >
                                                        {updateStatus.message}
                                                    </motion.div>
                                                )}

                                                <div className="flex items-center gap-3 p-3 rounded-lg bg-emerald-500/10 text-emerald-700 text-[10px] font-bold">
                                                    <Zap className="h-3 w-3" />
                                                    <span>기대 이익률: {(prediction.expected_margin_rate * 100).toFixed(1)}% ({prediction.impact})</span>
                                                </div>
                                            </div>
                                        ) : (
                                            <div className="p-4 rounded-xl bg-background/50 border border-primary/10 text-center">
                                                <p className="text-xs text-muted-foreground italic">가격 분석 데이터를 생성할 수 없습니다.</p>
                                            </div>
                                        )}
                                    </CardContent>
                                </Card>
                            </div>

                            {/* Action Plan */}
                            <section>
                                <h3 className="text-sm font-bold text-muted-foreground uppercase tracking-widest mb-4 flex items-center gap-2">
                                    <Lightbulb className="h-4 w-4 text-amber-500" /> 핵심 실행 계획 (Action Plan)
                                </h3>
                                <div className="grid gap-3">
                                    {report.action_plan.map((action, index) => (
                                        <motion.div
                                            key={index}
                                            initial={{ opacity: 0, x: -10 }}
                                            animate={{ opacity: 1, x: 0 }}
                                            transition={{ delay: index * 0.1 }}
                                            className="flex items-center gap-4 p-4 rounded-xl bg-accent/20 hover:bg-accent/30 transition-colors group"
                                        >
                                            <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center font-black text-primary text-sm shrink-0 group-hover:scale-110 transition-transform">
                                                {index + 1}
                                            </div>
                                            <p className="text-sm font-semibold">{action}</p>
                                        </motion.div>
                                    ))}
                                </div>
                            </section>
                        </div>
                    ) : (
                        <div className="text-center py-12">
                            <ShieldAlert className="h-12 w-12 text-destructive mx-auto mb-4" />
                            <p className="text-muted-foreground font-bold">보고서를 불러오지 못했습니다.</p>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="p-6 border-t bg-muted/30 flex justify-end">
                    <Button onClick={onClose} className="rounded-xl px-8 font-bold">
                        확인
                    </Button>
                </div>
            </motion.div>
        </div>
    );
}
