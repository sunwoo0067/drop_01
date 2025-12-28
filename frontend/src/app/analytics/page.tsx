"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BarChart3, RefreshCw, X } from "lucide-react";
import SalesSummaryCards from "@/components/analytics/SalesSummaryCards";
import ProductPerformanceTable from "@/components/analytics/ProductPerformanceTable";
import ProductOptionPerformanceTable from "@/components/analytics/ProductOptionPerformanceTable";
import SalesTrendChart from "@/components/analytics/SalesTrendChart";
import SourcingRecommendationDashboard from "@/components/analytics/SourcingRecommendationDashboard";
import StrategicReportModal from "@/components/analytics/StrategicReportModal";
import ChannelExpansionDashboard from "@/components/analytics/ChannelExpansionDashboard";
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
    const [selectedProduct, setSelectedProduct] = useState<{ id: string, name: string } | null>(null);
    const [analysisProduct, setAnalysisProduct] = useState<{ id: string, name: string } | null>(null);

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
                <ProductPerformanceTable
                    type="top"
                    limit={10}
                    onProductClick={(id, name) => setSelectedProduct({ id, name })}
                    onAIAnalysisClick={(id, name) => setAnalysisProduct({ id, name })}
                />
                <ProductPerformanceTable
                    type="low"
                    limit={10}
                    onProductClick={(id, name) => setSelectedProduct({ id, name })}
                    onAIAnalysisClick={(id, name) => setAnalysisProduct({ id, name })}
                />
            </motion.div>

            {/* Option Performance Details (Conditional) */}
            <AnimatePresence>
                {selectedProduct && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        variants={item}
                    >
                        <ProductOptionPerformanceTable
                            productId={selectedProduct.id}
                            productName={selectedProduct.name}
                            onClose={() => setSelectedProduct(null)}
                        />
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Strategic Analysis Modal (Conditional) */}
            <AnimatePresence>
                {analysisProduct && (
                    <StrategicReportModal
                        productId={analysisProduct.id}
                        productName={analysisProduct.name}
                        onClose={() => setAnalysisProduct(null)}
                    />
                )}
            </AnimatePresence>

            {/* Channel Expansion Dashboard */}
            <motion.div variants={item}>
                <ChannelExpansionDashboard />
            </motion.div>

            {/* Sourcing Recommendation Dashboard */}
            <motion.div variants={item}>
                <SourcingRecommendationDashboard />
            </motion.div>
        </motion.div>
    );
}
