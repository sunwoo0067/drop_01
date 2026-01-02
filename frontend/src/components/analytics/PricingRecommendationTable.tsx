"use client";

import { useEffect, useState, useCallback } from "react";
import {
    CheckCircle2,
    ArrowRight,
    RefreshCw,
    AlertTriangle,
    Check
} from "lucide-react";
import { analyticsClient } from "@/lib/analytics-api";
import type { PricingRecommendation } from "@/lib/types/analytics";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import {
    Table,
    TableHeader,
    TableBody,
    TableRow,
    TableHead,
    TableCell
} from "@/components/ui/Table";

export default function PricingRecommendationTable() {
    const [recommendations, setRecommendations] = useState<PricingRecommendation[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [applyingId, setApplyingId] = useState<string | null>(null);

    const fetchRecommendations = useCallback(async () => {
        try {
            setIsLoading(true);
            const data = await analyticsClient.getRecommendations("PENDING", 20);
            setRecommendations(data);
        } catch (error) {
            console.error("Failed to fetch recommendations:", error);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchRecommendations();
    }, [fetchRecommendations]);

    const handleApply = async (id: string) => {
        try {
            setApplyingId(id);
            const result = await analyticsClient.applyRecommendation(id);
            if (result.success) {
                // 성공 시 목록에서 제거
                setRecommendations(prev => prev.filter(r => r.id !== id));
            } else {
                alert(`적용 실패: ${result.message}`);
            }
        } catch (error) {
            console.error("Error applying recommendation:", error);
            alert("가격을 반영하는 중 오류가 발생했습니다.");
        } finally {
            setApplyingId(null);
        }
    };

    if (isLoading) {
        return <div className="p-8 text-center text-xs text-muted-foreground">권고 내역 로드 중...</div>;
    }

    if (recommendations.length === 0) {
        return (
            <div className="p-12 text-center border-2 border-dashed border-muted rounded-lg">
                <CheckCircle2 className="h-8 w-8 text-emerald-500 mx-auto mb-3 opacity-20" />
                <p className="text-sm font-medium text-muted-foreground">현재 처리할 가격 권고 사항이 없습니다.</p>
                <p className="text-[10px] text-muted-foreground mt-1">모든 상품이 안정적인 마진 구간에 있습니다.</p>
            </div>
        );
    }

    return (
        <div className="rounded-md border border-border overflow-hidden">
            <Table>
                <TableHeader className="bg-muted/30">
                    <TableRow>
                        <TableHead className="text-[10px] h-9">상품 정보</TableHead>
                        <TableHead className="text-[10px] h-9 text-right">현재가</TableHead>
                        <TableHead className="text-[10px] h-9"></TableHead>
                        <TableHead className="text-[10px] h-9 text-left">권장가</TableHead>
                        <TableHead className="text-[10px] h-9">예상 마진</TableHead>
                        <TableHead className="text-[10px] h-9">권고 사유</TableHead>
                        <TableHead className="text-[10px] h-9 text-right">조치</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {recommendations.map((rec) => {
                        const isIncrease = rec.recommended_price > rec.current_price;
                        const isRisk = rec.expected_margin && rec.expected_margin < 0.05;

                        return (
                            <TableRow key={rec.id} className="hover:bg-muted/10 transition-colors">
                                <TableCell className="py-2">
                                    <div className="flex flex-col">
                                        <span className="text-xs font-semibold truncate max-w-[200px]" title={rec.product_name}>
                                            {rec.product_name || "Unknown Product"}
                                        </span>
                                        <span className="text-[10px] text-muted-foreground font-mono">
                                            {rec.product_id.substring(0, 8)} | {rec.market_account_id.substring(0, 8)}
                                        </span>
                                    </div>
                                </TableCell>
                                <TableCell className="text-right text-xs py-2">
                                    {rec.current_price.toLocaleString()}원
                                </TableCell>
                                <TableCell className="py-2 px-1 text-center">
                                    <ArrowRight className={`h-3 w-3 ${isIncrease ? 'text-amber-500' : 'text-blue-500'} mx-auto`} />
                                </TableCell>
                                <TableCell className={`text-left text-xs font-bold py-2 ${isIncrease ? 'text-amber-600' : 'text-blue-600'}`}>
                                    {rec.recommended_price.toLocaleString()}원
                                </TableCell>
                                <TableCell className="py-2">
                                    <div className="flex items-center gap-1.5">
                                        <Badge
                                            variant={isRisk ? "destructive" : "outline"}
                                            className="text-[10px] px-1 h-5"
                                        >
                                            {(rec.expected_margin && rec.expected_margin * 100).toFixed(1)}%
                                        </Badge>
                                        {isRisk && <AlertTriangle className="h-3 w-3 text-destructive" />}
                                    </div>
                                </TableCell>
                                <TableCell className="py-2">
                                    <div className="flex flex-wrap gap-1 max-w-[250px]">
                                        {rec.reasons?.map((reason, idx) => (
                                            <span key={idx} className="bg-muted px-1.5 py-0.5 rounded-[2px] text-[9px] text-muted-foreground whitespace-nowrap">
                                                {reason}
                                            </span>
                                        ))}
                                    </div>
                                </TableCell>
                                <TableCell className="text-right py-2">
                                    <Button
                                        size="xs"
                                        className="h-7 px-3 bg-primary hover:bg-primary/90 text-[10px]"
                                        onClick={() => handleApply(rec.id)}
                                        disabled={applyingId === rec.id}
                                    >
                                        {applyingId === rec.id ? (
                                            <RefreshCw className="h-3 w-3 animate-spin" />
                                        ) : (
                                            <>
                                                <Check className="h-3 w-3 mr-1" />
                                                적용
                                            </>
                                        )}
                                    </Button>
                                </TableCell>
                            </TableRow>
                        );
                    })}
                </TableBody>
            </Table>
        </div>
    );
}
