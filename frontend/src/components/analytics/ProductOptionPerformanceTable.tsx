"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Layers, Package } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { analyticsAPI } from "@/lib/analytics-api";
import type { OptionPerformance } from "@/lib/types/analytics";

interface ProductOptionPerformanceTableProps {
    productId: string;
    productName: string;
    periodType?: "weekly" | "monthly";
    onClose?: () => void;
}

const container = {
    hidden: { opacity: 0, y: 20 },
    show: {
        opacity: 1, y: 0,
        transition: {
            staggerChildren: 0.05
        }
    }
};

const item = {
    hidden: { opacity: 0, x: -10 },
    show: { opacity: 1, x: 0 }
};

export default function ProductOptionPerformanceTable({
    productId,
    productName,
    periodType = "weekly",
    onClose
}: ProductOptionPerformanceTableProps) {
    const [performance, setPerformance] = useState<OptionPerformance[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        if (!productId) return;

        const fetchPerformance = async () => {
            try {
                setIsLoading(true);
                const data = await analyticsAPI.getProductOptionPerformance(productId, periodType);
                setPerformance(data);
            } catch (error) {
                console.error("Failed to fetch option performance:", error);
            } finally {
                setIsLoading(false);
            }
        };

        fetchPerformance();
    }, [productId, periodType]);

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

    if (isLoading) {
        return (
            <div className="space-y-4 animate-pulse">
                <div className="h-48 bg-muted rounded-2xl" />
            </div>
        );
    }

    return (
        <motion.div
            variants={container}
            initial="hidden"
            animate="show"
            className="space-y-4"
        >
            <Card className="border-2 border-primary/20 shadow-xl shadow-primary/5">
                <CardHeader className="flex flex-row items-center justify-between pb-4">
                    <CardTitle className="text-xl font-bold flex items-center gap-3">
                        <Layers className="h-6 w-6 text-primary" />
                        <span>[{productName}] 옵션별 성과 분석</span>
                    </CardTitle>
                    {onClose && (
                        <button
                            onClick={onClose}
                            className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                        >
                            닫기
                        </button>
                    )}
                </CardHeader>
                <CardContent>
                    {performance.length === 0 ? (
                        <div className="text-center py-12 text-muted-foreground bg-accent/20 rounded-xl border-2 border-dashed border-muted">
                            <Package className="h-12 w-12 mx-auto mb-3 opacity-20" />
                            <p className="font-medium">판매된 옵션 데이터가 없습니다.</p>
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full">
                                <thead>
                                    <tr className="text-xs font-bold uppercase tracking-widest text-muted-foreground border-b border-muted/50">
                                        <td className="py-4 pl-4">옵션명 / 값</td>
                                        <td className="py-4 text-center">판매수량</td>
                                        <td className="py-4 text-right">매출액</td>
                                        <td className="py-4 text-right">순이익</td>
                                        <td className="py-4 pr-4 text-right">수익률</td>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-muted/30">
                                    {performance.map((opt) => (
                                        <motion.tr
                                            key={opt.option_id}
                                            variants={item}
                                            className="hover:bg-accent/30 transition-colors"
                                        >
                                            <td className="py-4 pl-4">
                                                <div className="font-bold text-sm">{opt.option_name}</div>
                                                <div className="text-xs text-muted-foreground font-medium">{opt.option_value}</div>
                                            </td>
                                            <td className="py-4 text-center">
                                                <div className="inline-flex items-center justify-center px-2.5 py-1 rounded-full bg-blue-500/10 text-blue-500 font-bold text-xs ring-1 ring-inset ring-blue-500/20">
                                                    {opt.total_quantity.toLocaleString()}개
                                                </div>
                                            </td>
                                            <td className="py-4 text-right font-bold text-sm">
                                                {formatCurrency(opt.total_revenue)}
                                            </td>
                                            <td className="py-4 text-right">
                                                <div className="font-bold text-sm text-emerald-500">
                                                    {formatCurrency(opt.total_profit)}
                                                </div>
                                                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
                                                    Cost: {formatCurrency(opt.total_cost)}
                                                </div>
                                            </td>
                                            <td className="py-4 pr-4 text-right">
                                                <div className="flex items-center justify-end gap-1.5">
                                                    <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                                                        <div
                                                            className="h-full bg-emerald-500 transition-all duration-1000"
                                                            style={{ width: `${Math.min(opt.avg_margin_rate * 100, 100)}%` }}
                                                        />
                                                    </div>
                                                    <span className="text-xs font-black text-foreground">
                                                        {formatPercent(opt.avg_margin_rate)}
                                                    </span>
                                                </div>
                                            </td>
                                        </motion.tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </CardContent>
            </Card>
        </motion.div>
    );
}
