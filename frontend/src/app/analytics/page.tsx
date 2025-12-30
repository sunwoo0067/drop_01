"use client";

import { useState } from "react";
import { RefreshCw, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import SalesSummaryCards from "@/components/analytics/SalesSummaryCards";
import ProductPerformanceTable from "@/components/analytics/ProductPerformanceTable";
import ProductOptionPerformanceTable from "@/components/analytics/ProductOptionPerformanceTable";
import SourcingRecommendationDashboard from "@/components/analytics/SourcingRecommendationDashboard";
import ChannelExpansionDashboard from "@/components/analytics/ChannelExpansionDashboard";

export default function AnalyticsPage() {
    const [selectedProduct, setSelectedProduct] = useState<{ id: string, name: string } | null>(null);
    const [showCharts, setShowCharts] = useState(true);
    const [expandedSection, setExpandedSection] = useState<string | null>(null);

    const toggleSection = (sectionId: string) => {
        setExpandedSection(expandedSection === sectionId ? null : sectionId);
    };

    return (
        <div className="space-y-3">
            {/* Breadcrumb */}
            <Breadcrumb
                items={[
                    { label: "매출 분석" }
                ]}
            />

            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 border border-border bg-card rounded-sm">
                <div className="flex items-center gap-3">
                    <div className="h-6 w-6 rounded-sm bg-primary/10 flex items-center justify-center">
                        <RefreshCw className="h-3 w-3 text-primary" />
                    </div>
                    <div>
                        <h1 className="text-sm font-semibold text-foreground">매출 분석</h1>
                        <span className="text-[10px] text-muted-foreground">
                            매출 데이터, AI 예측, 소싱 추천 통합 뷰
                        </span>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowCharts(!showCharts)}
                    >
                        {showCharts ? <ChevronUp className="h-3 w-3 mr-1.5" /> : <ChevronDown className="h-3 w-3 mr-1.5" />}
                        차트 {showCharts ? "접기" : "펼치기"}
                    </Button>
                    <Button variant="outline" size="sm">
                        <RefreshCw className="h-3 w-3 mr-1.5" />
                        전체 새로고침
                    </Button>
                </div>
            </div>

            {/* Sales Summary Cards */}
            {showCharts && (
                <div className="px-4">
                    <SalesSummaryCards />
                </div>
            )}

            {/* Product Performance */}
            <div className="px-4">
                <Card className="border border-border">
                    <CardHeader
                        className="flex flex-row items-center justify-between pb-2 cursor-pointer"
                        onClick={() => toggleSection("product-performance")}
                    >
                        <CardTitle className="text-xs">상품 성과 분석</CardTitle>
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] text-muted-foreground">
                                {expandedSection === "product-performance" ? "접기" : "펼치기"}
                            </span>
                            {expandedSection === "product-performance" ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className={`transition-all ${expandedSection === "product-performance" || expandedSection === null ? "block" : "hidden"}`}>
                            <div className="grid gap-3 grid-cols-2">
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
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Option Performance Details (Conditional) */}
            {selectedProduct && (
                <div className="px-4">
                    <Card className="border border-border">
                        <CardHeader className="flex flex-row items-center justify-between pb-2">
                            <CardTitle className="text-xs">옵션 성과: {selectedProduct.name}</CardTitle>
                            <Button variant="ghost" size="xs" onClick={() => setSelectedProduct(null)}>
                                닫기
                            </Button>
                        </CardHeader>
                        <CardContent>
                            <ProductOptionPerformanceTable
                                productId={selectedProduct.id}
                                productName={selectedProduct.name}
                                onClose={() => setSelectedProduct(null)}
                            />
                        </CardContent>
                    </Card>
                </div>
            )}

            {/* Channel Expansion Dashboard */}
            <div className="px-4">
                <Card className="border border-border">
                    <CardHeader
                        className="flex flex-row items-center justify-between pb-2 cursor-pointer"
                        onClick={() => toggleSection("channel-expansion")}
                    >
                        <CardTitle className="text-xs">채널 확장 분석</CardTitle>
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] text-muted-foreground">
                                {expandedSection === "channel-expansion" ? "접기" : "펼치기"}
                            </span>
                            {expandedSection === "channel-expansion" ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className={`transition-all ${expandedSection === "channel-expansion" || expandedSection === null ? "block" : "hidden"}`}>
                            <ChannelExpansionDashboard />
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Sourcing Recommendation Dashboard */}
            <div className="px-4">
                <Card className="border border-border">
                    <CardHeader
                        className="flex flex-row items-center justify-between pb-2 cursor-pointer"
                        onClick={() => toggleSection("sourcing-recommendation")}
                    >
                        <CardTitle className="text-xs">소싱 추천</CardTitle>
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] text-muted-foreground">
                                {expandedSection === "sourcing-recommendation" ? "접기" : "펼치기"}
                            </span>
                            {expandedSection === "sourcing-recommendation" ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className={`transition-all ${expandedSection === "sourcing-recommendation" || expandedSection === null ? "block" : "hidden"}`}>
                            <SourcingRecommendationDashboard />
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
