'use client';

import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { BenchmarkProduct } from "@/lib/types/benchmark";
import { Button } from "@/components/ui/Button";
import { Loader2, Plus, RefreshCw, BarChart4, ClipboardList, Download } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";

import BenchmarkFilters from "./BenchmarkFilters";
import BenchmarkTable from "./BenchmarkTable";
import BenchmarkDetail from "./BenchmarkDetail";
import { Modal } from "@/components/ui/Modal";
import JobMonitor from "./JobMonitor";

export default function BenchmarkPage() {
    const [items, setItems] = useState<BenchmarkProduct[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'products' | 'jobs'>('products');

    // Filters State
    const [filters, setFilters] = useState({
        q: "",
        marketCode: "ALL",
        minPrice: "",
        maxPrice: "",
        minReviewCount: "",
        minRating: "",
        minQualityScore: "",
        orderBy: "created",
        offset: 0,
        limit: 50
    });

    // selection
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [isCollectionOpen, setIsCollectionOpen] = useState(false);

    const fetchBenchmarks = useCallback(async () => {
        setLoading(true);
        try {
            const params = { ...filters };
            // Map empty strings to undefined
            Object.keys(params).forEach(key => {
                if ((params as any)[key] === "") (params as any)[key] = undefined;
            });
            if (params.marketCode === 'ALL') params.marketCode = undefined;

            const response = await api.get('/benchmarks', { params });
            setItems(response.data.items || []);
            setTotal(response.data.total || 0);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [filters]);

    useEffect(() => {
        fetchBenchmarks();
    }, [fetchBenchmarks]);

    const handleDownloadCSV = () => {
        if (items.length === 0) return;

        const headers = ["마켓", "상품ID", "상품명", "가격", "평점", "리뷰", "품질점수", "카테고리경로", "URL"];
        const rows = items.map(p => [
            p.marketCode,
            `"${p.productId}"`,
            `"${p.name.replace(/"/g, '""')}"`,
            p.price,
            p.rating,
            p.reviewCount,
            p.qualityScore,
            `"${(p.categoryPath || '').replace(/"/g, '""')}"`,
            p.productUrl
        ]);

        const csvContent = [
            headers.join(","),
            ...rows.map(r => r.join(","))
        ].join("\n");

        // BOM for Excel (UTF-8)
        const blob = new Blob(["\uFEFF" + csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.setAttribute("href", url);
        link.setAttribute("download", `benchmarks_${new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    return (
        <div className="flex flex-col h-[calc(100vh-140px)] -m-6 box-border overflow-hidden">
            {/* Header Area */}
            <div className="flex items-center justify-between px-6 py-4 bg-background border-b z-10 shrink-0">
                <div>
                    <h1 className="text-2xl font-black tracking-tight flex items-center gap-2">
                        <BarChart4 className="h-6 w-6 text-primary" />
                        BENCHMARKS
                    </h1>
                    <p className="text-xs text-muted-foreground font-medium uppercase tracking-widest opacity-70">
                        Market Intelligence & Product Analysis
                    </p>
                </div>

                <div className="flex items-center gap-2">
                    <div className="flex bg-muted p-1 rounded-lg mr-4">
                        <Button
                            variant={activeTab === 'products' ? 'secondary' : 'ghost'}
                            size="sm"
                            className="h-8 px-4 text-xs font-semibold"
                            onClick={() => setActiveTab('products')}
                        >
                            <BarChart4 className="h-3.5 w-3.5 mr-2" />
                            상품 분석
                        </Button>
                        <Button
                            variant={activeTab === 'jobs' ? 'secondary' : 'ghost'}
                            size="sm"
                            className="h-8 px-4 text-xs font-semibold"
                            onClick={() => setActiveTab('jobs')}
                        >
                            <ClipboardList className="h-3.5 w-3.5 mr-2" />
                            수집 모니터
                        </Button>
                    </div>

                    <Button onClick={() => setIsCollectionOpen(true)} size="sm" className="h-9 px-4 shadow-md hover:shadow-lg transition-all">
                        <Plus className="mr-2 h-4 w-4" />
                        신규 수집
                    </Button>
                    <Button onClick={fetchBenchmarks} variant="outline" size="sm" className="h-9 w-9 p-0" disabled={loading}>
                        <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    </Button>
                </div>
            </div>

            {/* Content Area */}
            <div className="flex flex-1 overflow-hidden">
                {/* Left Sidebar: Filters or Jobs Info */}
                <aside className="w-72 border-r bg-muted/10 overflow-y-auto shrink-0 transition-all">
                    {activeTab === 'products' ? (
                        <BenchmarkFilters
                            filters={filters}
                            setFilters={setFilters}
                            onSearch={fetchBenchmarks}
                            isLoading={loading}
                        />
                    ) : (
                        <div className="p-4 space-y-4">
                            <h3 className="text-sm font-semibold">작업 상태 안내</h3>
                            <p className="text-xs text-muted-foreground leading-relaxed">
                                현재 진행 중인 수집 작업의 상태와 진행률을 확인하고, 실패한 작업을 재시도할 수 있습니다.
                            </p>
                            <div className="p-3 bg-blue-50 border border-blue-100 rounded-md">
                                <p className="text-[10px] text-blue-700 font-medium">
                                    TIP: 신규 수집을 시작하면 이곳에서 실시간 진행 상황이 업데이트됩니다.
                                </p>
                            </div>
                        </div>
                    )}
                </aside>

                {/* Main Panel: Results Table or Job History */}
                <main className="flex-1 flex flex-col min-w-0 bg-background relative overflow-hidden">
                    {activeTab === 'products' ? (
                        <>
                            <div className="flex-1 overflow-y-auto">
                                <BenchmarkTable
                                    items={items}
                                    selectedId={selectedId}
                                    onSelect={setSelectedId}
                                    isLoading={loading}
                                />
                            </div>
                            {/* Pagination/Status Area */}
                            <div className="p-4 border-t bg-muted/5 flex items-center justify-between text-xs text-muted-foreground shrink-0">
                                <span>총 {total}개의 상품</span>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-8 text-[11px] font-bold"
                                    onClick={handleDownloadCSV}
                                    disabled={items.length === 0}
                                >
                                    <Download className="h-3.5 w-3.5 mr-1" />
                                    CSV 내보내기
                                </Button>
                            </div>
                        </>
                    ) : (
                        <div className="p-6 max-w-2xl mx-auto w-full">
                            <JobMonitor />
                        </div>
                    )}
                </main>

                {/* Right Sidebar: Details (Dynamic) */}
                {selectedId && activeTab === 'products' && (
                    <aside className="w-[450px] shrink-0">
                        <BenchmarkDetail
                            id={selectedId}
                            onClose={() => setSelectedId(null)}
                        />
                    </aside>
                )}
            </div>

            <CollectionDialog
                isOpen={isCollectionOpen}
                onClose={() => setIsCollectionOpen(false)}
                onRefresh={() => {
                    setActiveTab('jobs'); // Switch to jobs tab to see progress
                }}
            />
        </div>
    );
}

// Inline for brevity in this overhaul, though should ideally be in its own file
function CollectionDialog({ isOpen, onClose, onRefresh }: { isOpen: boolean, onClose: () => void, onRefresh: () => void }) {
    const [marketCode, setMarketCode] = useState("ALL");
    const [categoryUrl, setCategoryUrl] = useState("");
    const [limit, setLimit] = useState(20);
    const [isLoading, setIsLoading] = useState(false);

    const handleSubmit = async () => {
        setIsLoading(true);
        try {
            await api.post('/benchmarks/collect/ranking', {
                marketCode,
                categoryUrl: categoryUrl || undefined,
                limit: Math.min(Math.max(limit, 1), 50)
            });
            onClose();
            onRefresh();
        } catch (err: any) {
            alert("수집 요청 실패: " + (err.response?.data?.detail || err.message));
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title="벤치마크 신규 수집"
            footer={
                <div className="flex gap-2 justify-end w-full">
                    <Button variant="ghost" onClick={onClose} disabled={isLoading}>취소</Button>
                    <Button onClick={handleSubmit} disabled={isLoading} className="bg-primary text-primary-foreground shadow-md">
                        {isLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                        수집 시작
                    </Button>
                </div>
            }
        >
            <div className="space-y-5 py-2">
                <Select
                    label="대상 마켓"
                    value={marketCode}
                    onChange={(e) => setMarketCode(e.target.value)}
                    options={[
                        { value: "ALL", label: "전체 마켓 (ALL)" },
                        { value: "COUPANG", label: "쿠팡 (Coupang)" },
                        { value: "NAVER_SHOPPING", label: "네이버쇼핑 (Naver)" },
                        { value: "GMARKET", label: "G마켓 (Gmarket)" },
                        { value: "AUCTION", label: "옥션 (Auction)" },
                        { value: "ELEVENST", label: "11번가 (11st)" },
                    ]}
                />

                <div className="space-y-1.5">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground block">카테고리 URL (선택)</label>
                    <Input
                        placeholder="마켓별 베스트/카테고리 URL 주소"
                        value={categoryUrl}
                        onChange={(e) => setCategoryUrl(e.target.value)}
                    />
                    <p className="text-[10px] text-muted-foreground/80 bg-muted/50 p-2 rounded border border-dashed leading-relaxed">
                        마켓 코드 <strong>ALL</strong> 선택 시 카테고리 URL은 무시되며 각 마켓의 전체 베스트 상품이 수집됩니다.
                    </p>
                </div>

                <div className="space-y-1.5">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground block">마켓별 수집 개수 (최대 50)</label>
                    <div className="flex items-center gap-4">
                        <Input
                            type="number"
                            min={1}
                            max={50}
                            value={limit}
                            onChange={(e) => setLimit(Number(e.target.value))}
                            className="w-24"
                        />
                        <div className="flex-1 h-2 bg-muted rounded-full relative">
                            <div
                                className="absolute inset-y-0 left-0 bg-primary rounded-full transition-all"
                                style={{ width: `${(limit / 50) * 100}%` }}
                            />
                        </div>
                    </div>
                </div>
            </div>
        </Modal>
    );
}
