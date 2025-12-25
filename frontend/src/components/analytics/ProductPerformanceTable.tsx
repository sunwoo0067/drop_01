"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, Package, ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { analyticsAPI } from "@/lib/analytics-api";
import type { ProductPerformance } from "@/lib/types/analytics";

interface ProductPerformanceTableProps {
    type: "top" | "low";
    limit?: number;
    periodType?: "weekly" | "monthly";
}

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
    hidden: { opacity: 0, x: -20 },
    show: { opacity: 1, x: 0 }
};

export default function ProductPerformanceTable({
    type,
    limit = 10,
    periodType = "weekly"
}: ProductPerformanceTableProps) {
    const [products, setProducts] = useState<ProductPerformance[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    const fetchProducts = async () => {
        try {
            setIsLoading(true);
            const data = type === "top"
                ? await analyticsAPI.getTopPerforming(limit, periodType)
                : await analyticsAPI.getLowPerforming(limit, periodType);
            setProducts(data);
        } catch (error) {
            console.error(`Failed to fetch ${type} performing products:`, error);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchProducts();
    }, [type, limit, periodType]);

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
        if (value < 0) return <TrendingDown className="h-4 w-4" />;
        return null;
    };

    const title = type === "top" ? "상위 성과 제품" : "저성과 제품";
    const iconColor = type === "top" ? "text-emerald-500" : "text-red-500";
    const bgColor = type === "top" ? "bg-emerald-500/10" : "bg-red-500/10";

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Package className={`h-5 w-5 ${iconColor}`} />
                        {title}
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="space-y-3">
                        {[...Array(5)].map((_, i) => (
                            <div key={i} className="flex items-center gap-4 animate-pulse">
                                <div className="h-10 w-10 bg-muted rounded-lg" />
                                <div className="flex-1 space-y-2">
                                    <div className="h-4 w-3/4 bg-muted rounded" />
                                    <div className="h-3 w-1/2 bg-muted rounded" />
                                </div>
                            </div>
                        ))}
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                    <Package className={`h-5 w-5 ${iconColor}`} />
                    {title}
                </CardTitle>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={fetchProducts}
                    className="text-xs"
                >
                    새로고침
                </Button>
            </CardHeader>
            <CardContent>
                {products.length === 0 ? (
                    <div className="text-center py-8 text-sm text-muted-foreground">
                        데이터가 없습니다.
                    </div>
                ) : (
                    <motion.div
                        variants={container}
                        initial="hidden"
                        animate="show"
                        className="space-y-3"
                    >
                        {products.map((product, index) => (
                            <motion.div
                                key={product.product_id}
                                variants={item}
                                className="flex items-center gap-4 p-3 rounded-xl hover:bg-accent/50 transition-colors group cursor-pointer"
                            >
                                {/* Rank Badge */}
                                <div
                                    className={`h-10 w-10 rounded-lg ${bgColor} flex items-center justify-center font-black text-sm ${iconColor}`}
                                >
                                    {index + 1}
                                </div>

                                {/* Product Info */}
                                <div className="flex-1 min-w-0">
                                    <div className="font-semibold text-sm truncate">
                                        {product.product_name}
                                    </div>
                                    <div className="text-xs text-muted-foreground mt-0.5">
                                        {product.total_orders.toLocaleString()} 주문
                                    </div>
                                </div>

                                {/* Revenue */}
                                <div className="text-right">
                                    <div className="font-bold text-sm">
                                        {formatCurrency(product.total_revenue)}
                                    </div>
                                    <div className="text-xs text-muted-foreground">
                                        이익률: {formatPercent(product.avg_margin_rate)}
                                    </div>
                                </div>

                                {/* Growth */}
                                <div className={`flex items-center gap-1 text-sm font-bold ${getGrowthColor(product.revenue_growth_rate)}`}>
                                    {getGrowthIcon(product.revenue_growth_rate)}
                                    <span>{formatPercent(product.revenue_growth_rate)}</span>
                                </div>

                                {/* Chevron */}
                                <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                            </motion.div>
                        ))}
                    </motion.div>
                )}
            </CardContent>
        </Card>
    );
}
