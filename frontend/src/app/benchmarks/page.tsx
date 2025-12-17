'use client';

import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { BenchmarkProduct } from "@/lib/types/benchmark";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { Loader2, ExternalLink, RefreshCw, Search, Plus, Radio, AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/Badge";

// --- Types ---

interface BenchmarkCollectJob {
    id: string;
    status: string;
    marketCode: string;
    progress: number;
    failedMarkets: string[];
    lastError: string | null;
    createdAt: string;
}

// --- Components ---

function JobStatusCard({ job }: { job: BenchmarkCollectJob }) {
    const isRunning = job.status === "running" || job.status === "queued";
    const statusColor =
        job.status === "succeeded" ? "text-green-600 border-green-200 bg-green-50" :
            job.status === "failed" ? "text-destructive border-red-200 bg-red-50" :
                "text-primary border-blue-200 bg-blue-50";

    return (
        <div className={`flex items-center justify-between p-3 rounded-md border ${statusColor} text-sm mb-2`}>
            <div className="flex items-center gap-2">
                {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> :
                    job.status === "succeeded" ? <div className="h-2 w-2 rounded-full bg-green-500" /> :
                        <AlertCircle className="h-4 w-4" />
                }
                <span className="font-medium">{job.marketCode} 수집 ({job.status})</span>
                {job.progress > 0 && <span className="text-xs opacity-75"> - {job.progress}%</span>}
            </div>
            <span className="text-xs opacity-75">{new Date(job.createdAt).toLocaleTimeString()}</span>
        </div>
    );
}

function CollectionDialog({ isOpen, onClose, onRefresh }: { isOpen: boolean, onClose: () => void, onRefresh: () => void }) {
    const [marketCode, setMarketCode] = useState("COUPANG");
    const [categoryUrl, setCategoryUrl] = useState("");
    const [limit, setLimit] = useState(10);
    const [isLoading, setIsLoading] = useState(false);

    const handleSubmit = async () => {
        setIsLoading(true);
        try {
            await api.post('/benchmarks/collect/ranking', {
                marketCode,
                categoryUrl: categoryUrl || undefined,
                limit
            });
            onClose();
            onRefresh(); // Trigger status refresh
        } catch (err: any) {
            console.error(err);
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
                <>
                    <Button variant="ghost" onClick={onClose} disabled={isLoading}>취소</Button>
                    <Button onClick={handleSubmit} disabled={isLoading}>
                        {isLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                        수집 시작
                    </Button>
                </>
            }
        >
            <div className="space-y-4">
                <Select
                    label="마켓 선택"
                    value={marketCode}
                    onChange={(e) => setMarketCode(e.target.value)}
                    options={[
                        { value: "COUPANG", label: "쿠팡 (Coupang)" },
                        { value: "NAVER_SHOPPING", label: "네이버쇼핑 (Naver)" },
                        { value: "GMARKET", label: "G마켓 (Gmarket)" },
                        { value: "ELEVENST", label: "11번가 (11st)" },
                    ]}
                />

                <div>
                    <label className="text-sm font-medium mb-1 block">카테고리 URL (선택)</label>
                    <Input
                        placeholder="https://www.coupang.com/np/categories/..."
                        value={categoryUrl}
                        onChange={(e) => setCategoryUrl(e.target.value)}
                    />
                    <p className="text-xs text-muted-foreground mt-1">입력하지 않으면 기본 랭킹 페이지를 수집합니다.</p>
                </div>

                <div>
                    <label className="text-sm font-medium mb-1 block">수집 개수 (최대 50)</label>
                    <Input
                        type="number"
                        min={1}
                        max={50}
                        value={limit}
                        onChange={(e) => setLimit(Number(e.target.value))}
                    />
                </div>
            </div>
        </Modal>
    );
}

// --- Main Page ---

export default function BenchmarkPage() {
    const [benchmarks, setBenchmarks] = useState<BenchmarkProduct[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Filters
    const [searchQuery, setSearchQuery] = useState("");
    const [marketFilter, setMarketFilter] = useState("");
    const [sortOrder, setSortOrder] = useState("created");

    // Collection State
    const [isCollectionOpen, setIsCollectionOpen] = useState(false);
    const [activeJobs, setActiveJobs] = useState<BenchmarkCollectJob[]>([]);

    const fetchBenchmarks = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const params: any = {
                limit: 50,
                orderBy: sortOrder
            };
            if (searchQuery) params.q = searchQuery;
            if (marketFilter && marketFilter !== 'ALL') params.marketCode = marketFilter;

            const response = await api.get('/benchmarks', { params });
            setBenchmarks(response.data);
        } catch (err: any) {
            console.error(err);
            setError("벤치마크 데이터를 불러오는데 실패했습니다.");
        } finally {
            setLoading(false);
        }
    }, [searchQuery, marketFilter, sortOrder]);

    const fetchJobs = async () => {
        try {
            const response = await api.get('/benchmarks/jobs', { params: { limit: 5 } });
            setActiveJobs(response.data);
        } catch (err) {
            console.error("Failed to fetch jobs", err);
        }
    };

    // Initial Load & Job Polling
    useEffect(() => {
        fetchBenchmarks();
        fetchJobs();
        const interval = setInterval(fetchJobs, 5000); // Poll jobs every 5s
        return () => clearInterval(interval);
    }, [fetchBenchmarks]);

    return (
        <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">벤치마크 상품</h1>
                    <p className="text-muted-foreground mt-2">
                        경쟁사/시장 벤치마크 상품을 수집하고 분석합니다.
                    </p>
                </div>
                <div className="flex gap-2">
                    <Button onClick={() => setIsCollectionOpen(true)}>
                        <Plus className="mr-2 h-4 w-4" />
                        신규 수집
                    </Button>
                    <Button onClick={fetchBenchmarks} variant="outline" disabled={loading}>
                        <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    </Button>
                </div>
            </div>

            {/* Job Status Section */}
            {activeJobs.length > 0 && activeJobs.some(j => j.status === 'running' || j.status === 'queued') && (
                <div className="bg-muted/30 p-4 rounded-lg border">
                    <h3 className="text-sm font-semibold mb-3 flex items-center">
                        <Loader2 className="h-3 w-3 mr-2 animate-spin" />
                        진행 중인 수집 작업
                    </h3>
                    {activeJobs.filter(j => j.status === 'running' || j.status === 'queued').map(job => (
                        <JobStatusCard key={job.id} job={job} />
                    ))}
                </div>
            )}

            {/* Filter Bar */}
            <div className="flex flex-col md:flex-row gap-4 bg-background p-4 rounded-lg border shadow-sm items-end">
                <div className="w-full md:w-1/3">
                    <label className="text-sm font-medium mb-1 block">검색</label>
                    <div className="relative">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input
                            className="pl-9"
                            placeholder="상품명 검색..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && fetchBenchmarks()}
                        />
                    </div>
                </div>
                <div className="w-full md:w-1/4">
                    <Select
                        label="마켓"
                        options={[
                            { value: "ALL", label: "전체" },
                            { value: "COUPANG", label: "쿠팡" },
                            { value: "NAVER_SHOPPING", label: "네이버쇼핑" },
                            { value: "GMARKET", label: "G마켓" },
                            { value: "ELEVENST", label: "11번가" },
                        ]}
                        value={marketFilter}
                        onChange={(e) => setMarketFilter(e.target.value)}
                    />
                </div>
                <div className="w-full md:w-1/4">
                    <Select
                        label="정렬"
                        options={[
                            { value: "created", label: "최신순" },
                            { value: "updated", label: "업데이트순" },
                        ]}
                        value={sortOrder}
                        onChange={(e) => setSortOrder(e.target.value)}
                    />
                </div>
                <Button variant="secondary" onClick={fetchBenchmarks} className="w-full md:w-auto">
                    조회
                </Button>
            </div>

            {error && (
                <div className="bg-destructive/15 text-destructive p-4 rounded-md flex items-center">
                    <AlertCircle className="h-4 w-4 mr-2" />
                    {error}
                </div>
            )}

            {loading && benchmarks.length === 0 ? (
                <div className="flex justify-center items-center h-64">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                    {benchmarks.map((item) => (
                        <Card key={item.id} className="overflow-hidden hover:shadow-lg transition-transform hover:-translate-y-1 duration-200 group">
                            <div className="aspect-square relative bg-muted/20 overflow-hidden">
                                {item.imageUrls && item.imageUrls.length > 0 ? (
                                    <img
                                        src={item.imageUrls[0]}
                                        alt={item.name}
                                        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                                        loading="lazy"
                                    />
                                ) : (
                                    <div className="flex items-center justify-center h-full text-muted-foreground">
                                        No Image
                                    </div>
                                )}
                                <div className="absolute top-2 right-2">
                                    <Badge variant="secondary" className="bg-black/50 text-white backdrop-blur-sm border-0">
                                        {item.marketCode}
                                    </Badge>
                                </div>
                            </div>
                            <CardHeader className="p-4 pb-2">
                                <CardTitle className="text-base line-clamp-2 min-h-[3rem]" title={item.name}>
                                    {item.name}
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="p-4 pt-0 space-y-2">
                                <div className="font-bold text-lg text-primary">
                                    {item.price.toLocaleString()}원
                                </div>
                                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                                    <span className={`px-1.5 py-0.5 rounded ${item.detailHtmlLen > 0 ? "bg-green-100 text-green-700" : "bg-gray-100"}`}>
                                        {item.detailHtmlLen > 0 ? '상세보유' : '상세없음'}
                                    </span>
                                </div>
                            </CardContent>
                            <CardFooter className="p-4 pt-0 bg-muted/5 mt-auto">
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="w-full text-muted-foreground hover:text-primary"
                                    onClick={() => window.open(item.productUrl, '_blank')}
                                >
                                    <ExternalLink className="h-4 w-4 mr-2" />
                                    상품 원문 보기
                                </Button>
                            </CardFooter>
                        </Card>
                    ))}
                    {!loading && benchmarks.length === 0 && (
                        <div className="col-span-full flex flex-col items-center justify-center py-16 text-muted-foreground bg-muted/10 rounded-lg border border-dashed">
                            <Search className="h-10 w-10 mb-4 opacity-20" />
                            <p className="text-lg font-medium">수집된 벤치마크 상품이 없습니다.</p>
                            <p className="text-sm mt-1">상단의 '신규 수집' 버튼을 눌러 데이터를 수집해보세요.</p>
                        </div>
                    )}
                </div>
            )}

            <CollectionDialog
                isOpen={isCollectionOpen}
                onClose={() => setIsCollectionOpen(false)}
                onRefresh={() => {
                    fetchJobs();
                    // Optional: fetchBenchmarks() after a delay or let the user refresh manually
                }}
            />
        </div>
    );
}
