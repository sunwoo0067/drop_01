"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
    Share2,
    Zap,
    ChevronRight,
    Loader2,
    ArrowRightLeft,
    Coins,
    CheckCircle2
} from "lucide-react";
import { analyticsClient } from "@/lib/analytics-api";
import type { ScalingRecommendation } from "@/lib/types/analytics";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

export default function ChannelExpansionDashboard() {
    const [recommendations, setRecommendations] = useState<ScalingRecommendation[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [expandingId, setExpandingId] = useState<string | null>(null);

    useEffect(() => {
        const fetchRecommendations = async () => {
            try {
                setIsLoading(true);
                const data = await analyticsClient.getScalingRecommendations(10);
                setRecommendations(data);
            } catch (error) {
                console.error("Failed to fetch scaling recommendations:", error);
            } finally {
                setIsLoading(false);
            }
        };

        fetchRecommendations();
    }, []);

    const handleExpand = async (rec: ScalingRecommendation) => {
        // 실제 마켓 등록 연동은 다음 단계에서 고도화 예정
        setExpandingId(rec.product_id);
        setTimeout(() => {
            setExpandingId(null);
            alert(`${rec.product_name} 상품을 ${rec.target_market} 채널로 확장 등록 요청을 보냈습니다. (프로토타입)`);
        }, 1500);
    };

    if (isLoading) {
        return (
            <div className="h-64 flex flex-col items-center justify-center gap-4">
                <Loader2 className="h-10 w-10 text-primary animate-spin" />
                <p className="text-muted-foreground font-bold animate-pulse">
                    마켓별 성과 데이터를 교차 분석하여 확장 기회를 찾고 있습니다...
                </p>
            </div>
        );
    }

    if (recommendations.length === 0) {
        return (
            <Card className="border-dashed bg-muted/20">
                <CardContent className="h-48 flex flex-col items-center justify-center text-center p-6">
                    <Share2 className="h-10 w-10 text-muted-foreground/40 mb-3" />
                    <p className="text-sm font-bold text-muted-foreground">현재 추천할 수 있는 다채널 확장 기회가 없습니다.</p>
                    <p className="text-xs text-muted-foreground/60 mt-1">판매량이 높은 우수 상품이 확보되면 자동으로 추천됩니다.</p>
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col gap-1">
                <h3 className="text-lg font-black tracking-tight flex items-center gap-2">
                    <Share2 className="h-5 w-5 text-primary" /> 다채널 스케일업 가이드
                </h3>
                <p className="text-sm text-muted-foreground font-medium">
                    특정 마켓에서 검증된 우승 상품을 타 채널로 확장하여 매출을 극대화하세요.
                </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                <AnimatePresence>
                    {recommendations.map((rec, index) => (
                        <motion.div
                            key={`${rec.product_id}-${rec.target_market}`}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: index * 0.1 }}
                        >
                            <Card className="group overflow-hidden border-primary/10 hover:border-primary/30 transition-all hover:shadow-xl hover:shadow-primary/5 rounded-3xl h-full flex flex-col">
                                <CardContent className="p-0 flex-1 flex flex-col">
                                    {/* Header */}
                                    <div className="p-5 bg-gradient-to-br from-primary/5 to-transparent border-b border-primary/5">
                                        <div className="flex justify-between items-start mb-3">
                                            <div className={cn(
                                                "px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-tighter",
                                                rec.expected_impact === 'High' ? "bg-orange-500 text-white" : "bg-blue-500 text-white"
                                            )}>
                                                {rec.expected_impact} Impact
                                            </div>
                                            <div className="flex items-center gap-1.5 p-1 px-2 rounded-lg bg-emerald-500/10 text-emerald-600 text-[10px] font-black uppercase">
                                                <CheckCircle2 className="h-3 w-3" />
                                                Verified
                                            </div>
                                        </div>
                                        <h4 className="text-sm font-black line-clamp-1 group-hover:text-primary transition-colors">
                                            {rec.product_name}
                                        </h4>
                                    </div>

                                    {/* Body */}
                                    <div className="p-5 space-y-4 flex-1">
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-3">
                                                <div className="h-8 w-8 rounded-xl bg-card border shadow-sm flex items-center justify-center font-black text-[10px] text-muted-foreground">
                                                    {rec.source_market.substring(0, 2)}
                                                </div>
                                                <ArrowRightLeft className="h-3 w-3 text-muted-foreground/40" />
                                                <div className="h-8 w-8 rounded-xl bg-primary/10 border-primary/20 shadow-sm flex items-center justify-center font-black text-[10px] text-primary">
                                                    {rec.target_market.substring(0, 2)}
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <span className="text-[10px] font-bold text-muted-foreground block uppercase">Current Velocity</span>
                                                <span className="text-sm font-black">주간 {rec.current_orders}건+</span>
                                            </div>
                                        </div>

                                        <div className="space-y-2">
                                            <div className="flex items-center justify-between text-[10px] font-bold text-muted-foreground uppercase">
                                                <span>Difficulty</span>
                                                <span className={cn(
                                                    rec.difficulty_score === 'Low' ? "text-emerald-500" : "text-amber-500"
                                                )}>{rec.difficulty_score}</span>
                                            </div>
                                            <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                                                <div
                                                    className={cn(
                                                        "h-full rounded-full",
                                                        rec.difficulty_score === 'Low' ? "bg-emerald-500 w-1/3" : "bg-amber-500 w-2/3"
                                                    )}
                                                />
                                            </div>
                                        </div>

                                        <div className="p-3 rounded-2xl bg-accent/30 border border-primary/5 text-xs font-medium leading-relaxed italic">
                                            "{rec.reason}"
                                        </div>

                                        <div className="flex items-center gap-2 mt-auto pt-2">
                                            <div className="flex-1 p-3 rounded-2xl bg-primary/5 border border-primary/10 flex flex-col items-center justify-center text-center">
                                                <span className="text-[9px] font-bold text-muted-foreground block uppercase mb-1">Potential Monthly Revenue</span>
                                                <div className="flex items-center gap-1 text-primary">
                                                    <Coins className="h-3 w-3" />
                                                    <span className="text-xs font-black">약 {(rec.potential_revenue / 10000).toFixed(0)}만원+</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Action */}
                                    <div className="p-4 pt-0">
                                        <Button
                                            onClick={() => handleExpand(rec)}
                                            disabled={expandingId === rec.product_id}
                                            className="w-full rounded-2xl font-black gap-2 h-11 shadow-lg shadow-primary/10 overflow-hidden relative group"
                                        >
                                            {expandingId === rec.product_id ? (
                                                <Loader2 className="h-4 w-4 animate-spin text-white" />
                                            ) : (
                                                <>
                                                    <Zap className="h-4 w-4 fill-current text-white group-hover:scale-125 transition-transform" />
                                                    {rec.target_market} 채널 확장하기
                                                    <ChevronRight className="h-4 w-4 absolute right-4 opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
                                                </>
                                            )}
                                        </Button>
                                    </div>
                                </CardContent>
                            </Card>
                        </motion.div>
                    ))}
                </AnimatePresence>
            </div>
        </div>
    );
}
