"use client";

import { motion } from "framer-motion";
import { BarChart3, RefreshCw } from "lucide-react";
import SalesSummaryCards from "@/components/analytics/SalesSummaryCards";
import ProductPerformanceTable from "@/components/analytics/ProductPerformanceTable";
import SalesTrendChart from "@/components/analytics/SalesTrendChart";
import SourcingRecommendationDashboard from "@/components/analytics/SourcingRecommendationDashboard";
import { Button } from "@/components/ui/Button";

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

export default function AnalyticsPage() {
    return (
        <motion.div
            variants={container}
            initial="hidden"
            animate="show"
            className="space-y-8 py-6"
        >
            {/* Header */}
            <motion.div variants={item} className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                    <h1 className="text-4xl font-black tracking-tight bg-gradient-to-r from-foreground to-foreground/60 bg-clip-text text-transparent">
                        매출 등대
                    </h1>
                    <Button variant="outline" size="sm">
                        <RefreshCw className="h-4 w-4 mr-2" />
                        전체 새로고침
                    </Button>
                </div>
                <p className="text-muted-foreground font-medium">
                    매출 데이터, AI 예측, 소싱 추천을 통합한 대시보드입니다.
                </p>
            </motion.div>

            {/* Sales Summary Cards */}
            <motion.div variants={item}>
                <SalesSummaryCards />
            </motion.div>

            {/* Sales Trend Chart */}
            <motion.div variants={item}>
                <SalesTrendChart />
            </motion.div>

            {/* Product Performance Tables */}
            <motion.div variants={item} className="grid gap-6 md:grid-cols-2">
                <ProductPerformanceTable type="top" limit={10} />
                <ProductPerformanceTable type="low" limit={10} />
            </motion.div>

            {/* Sourcing Recommendation Dashboard */}
            <motion.div variants={item}>
                <SourcingRecommendationDashboard />
            </motion.div>
        </motion.div>
    );
}
