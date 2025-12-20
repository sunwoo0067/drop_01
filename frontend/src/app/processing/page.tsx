"use client";

import { useEffect, useState } from "react";
import {
    Loader2,
    Search,
    Filter,
    Wand2,
    CheckCircle2,
    Clock,
    XCircle,
    AlertCircle,
    RotateCw,
    ExternalLink,
    ChevronRight,
    Sparkles
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import api from "@/lib/api";
import { Product } from "@/types";
import { cn } from "@/lib/utils";

export default function ProcessingPage() {
    const [items, setItems] = useState<Product[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState("");
    const [processingIds, setProcessingIds] = useState<Set<string>>(new Set());

    const fetchProducts = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await api.get("/products/");
            setItems(Array.isArray(response.data) ? response.data : []);
        } catch (e) {
            console.error("Failed to fetch products", e);
            setError("상품 목록을 불러오지 못했습니다.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchProducts();
    }, []);

    const handleProcess = async (productId: string) => {
        if (processingIds.has(productId)) return;

        setProcessingIds(prev => new Set(prev).add(productId));
        try {
            await api.post(`/products/${productId}/process`, {
                minImagesRequired: 3,
                forceFetchOwnerClan: false
            });
            // Refresh status after a short delay or poll
            setTimeout(fetchProducts, 2000);
        } catch (e) {
            console.error("Processing failed", e);
            alert("가공 트리거 실패");
        } finally {
            setProcessingIds(prev => {
                const next = new Set(prev);
                next.delete(productId);
                return next;
            });
        }
    };

    const handleProcessPending = async () => {
        try {
            await api.post("/products/process/pending", null, {
                params: { limit: 10, minImagesRequired: 3 }
            });
            alert("대기 중인 상품들에 대해 가공이 시작되었습니다.");
            setTimeout(fetchProducts, 1000);
        } catch (e) {
            console.error("Batch processing failed", e);
        }
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case "COMPLETED": return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
            case "PROCESSING": return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
            case "FAILED": return <XCircle className="h-4 w-4 text-destructive" />;
            default: return <Clock className="h-4 w-4 text-muted-foreground" />;
        }
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case "COMPLETED": return <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-200">가공 완료</Badge>;
            case "PROCESSING": return <Badge className="bg-blue-500/10 text-blue-600 border-blue-200">가공 중</Badge>;
            case "FAILED": return <Badge variant="destructive" className="bg-destructive/10 text-destructive border-destructive/20">가공 실패</Badge>;
            default: return <Badge variant="secondary">가공 대기</Badge>;
        }
    };

    const filteredItems = items.filter(item =>
        item.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.processed_name?.toLowerCase().includes(searchTerm.toLowerCase())
    );

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
            {/* Header Section */}
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 pb-6 border-b">
                <div className="space-y-2">
                    <div className="flex items-center gap-2 text-primary font-medium">
                        <Wand2 className="h-5 w-5" />
                        <span>Work Management</span>
                    </div>
                    <h1 className="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
                        상품 가공 센터
                    </h1>
                    <p className="text-muted-foreground max-w-2xl">
                        AI를 사용하여 상품명을 최적화하고 이미지를 가공합니다. 고유한 콘텐츠를 생성하여 마켓 노출 확률을 높입니다.
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <Button variant="outline" className="rounded-xl h-11 px-6 border-2 hover:bg-accent" onClick={fetchProducts}>
                        <RotateCw className="mr-2 h-4 w-4" />
                        새로고침
                    </Button>
                    <Button className="rounded-xl h-11 px-6 shadow-lg shadow-primary/20 hover:scale-105 transition-transform" onClick={handleProcessPending}>
                        <Sparkles className="mr-2 h-4 w-4" />
                        일괄 가공 시작
                    </Button>
                </div>
            </div>

            {/* Search and Filters */}
            <div className="flex flex-col md:flex-row gap-4 items-center">
                <div className="relative flex-1 group w-full">
                    <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground group-focus-within:text-primary transition-colors" />
                    <Input
                        placeholder="가공 중인 상품 또는 최적화된 이름搜索..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="pl-12 h-12 rounded-2xl border-none bg-accent/50 focus-visible:ring-2 focus-visible:ring-primary/20 transition-all text-base w-full"
                    />
                </div>
                <Button variant="outline" className="h-12 rounded-2xl px-6 border-2 shrink-0 bg-background/50 backdrop-blur-sm">
                    <Filter className="mr-2 h-4 w-4" />
                    상태 필터
                </Button>
            </div>

            {/* Product List */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {loading ? (
                    <div className="col-span-full h-80 flex flex-col items-center justify-center space-y-4">
                        <div className="h-12 w-12 rounded-full border-4 border-primary/20 border-t-primary animate-spin" />
                        <p className="text-muted-foreground font-medium animate-pulse">상품 데이터를 불러오는 중...</p>
                    </div>
                ) : error ? (
                    <Card className="col-span-full border-2 border-destructive/20 bg-destructive/5">
                        <CardContent className="flex flex-col items-center py-12 text-center">
                            <AlertCircle className="h-12 w-12 text-destructive mb-4" />
                            <h3 className="text-xl font-bold mb-2">오류 발생</h3>
                            <p className="text-muted-foreground">{error}</p>
                            <Button className="mt-6 rounded-xl" variant="outline" onClick={fetchProducts}>다시 시도</Button>
                        </CardContent>
                    </Card>
                ) : filteredItems.length === 0 ? (
                    <div className="col-span-full py-20 text-center">
                        <div className="h-20 w-20 bg-accent rounded-full flex items-center justify-center mx-auto mb-6">
                            <Search className="h-10 w-10 text-muted-foreground/50" />
                        </div>
                        <h3 className="text-2xl font-bold text-foreground mb-2">대상 상품이 없습니다</h3>
                        <p className="text-muted-foreground">소싱 페이지에서 상품을 승격시켜 가공을 시작해 보세요.</p>
                        <Button className="mt-8 rounded-xl h-11 px-8" onClick={() => window.location.href = '/sourcing'}>소싱 페이지로 이동</Button>
                    </div>
                ) : (
                    filteredItems.map((item) => (
                        <Card key={item.id} className="group overflow-hidden border-none shadow-md hover:shadow-2xl transition-all duration-500 rounded-3xl bg-card/40 backdrop-blur-xl border border-white/10">
                            {/* Image Preview */}
                            <div className="aspect-[4/3] relative overflow-hidden bg-muted group-hover:cursor-pointer">
                                {item.processed_image_urls && item.processed_image_urls.length > 0 ? (
                                    <img
                                        src={item.processed_image_urls[0]}
                                        alt={item.name}
                                        className="object-cover w-full h-full transition-transform duration-700 group-hover:scale-110"
                                    />
                                ) : (
                                    <div className="w-full h-full flex flex-col items-center justify-center text-muted-foreground/30 space-y-2">
                                        <Wand2 className="h-12 w-12" />
                                        <span className="text-xs font-medium uppercase tracking-widest">No Image Yet</span>
                                    </div>
                                )}

                                {/* Overlay Status */}
                                <div className="absolute top-4 left-4 flex gap-2">
                                    <Badge className="bg-black/40 backdrop-blur-md border-0 text-[10px] font-bold tracking-widest uppercase py-1">
                                        {item.status}
                                    </Badge>
                                </div>
                                <div className="absolute top-4 right-4 translate-x-12 opacity-0 group-hover:translate-x-0 group-hover:opacity-100 transition-all duration-300">
                                    <Button size="icon" variant="secondary" className="h-9 w-9 rounded-full shadow-lg">
                                        <ExternalLink className="h-4 w-4" />
                                    </Button>
                                </div>
                            </div>

                            <CardContent className="p-5 space-y-4">
                                <div className="space-y-1">
                                    <div className="flex items-center gap-2 mb-1">
                                        {getStatusIcon(item.processing_status)}
                                        {getStatusBadge(item.processing_status)}
                                    </div>
                                    <h3 className="font-bold text-lg leading-tight truncate-2-lines group-hover:text-primary transition-colors">
                                        {item.processed_name || item.name}
                                    </h3>
                                    {item.processed_name && (
                                        <p className="text-xs text-muted-foreground line-through opacity-50 truncate">
                                            {item.name}
                                        </p>
                                    )}
                                </div>

                                <div className="flex items-center justify-between text-sm py-3 border-y border-foreground/5">
                                    <div className="flex flex-col">
                                        <span className="text-muted-foreground text-[10px] uppercase font-bold tracking-tighter">Selling Price</span>
                                        <span className="font-bold text-base text-primary">{item.selling_price.toLocaleString()}원</span>
                                    </div>
                                    <div className="flex flex-col items-end">
                                        <span className="text-muted-foreground text-[10px] uppercase font-bold tracking-tighter">Images</span>
                                        <span className="font-semibold">{item.processed_image_urls?.length || 0}개</span>
                                    </div>
                                </div>

                                <div className="flex flex-wrap gap-1.5">
                                    {item.processed_keywords?.slice(0, 3).map((kw, idx) => (
                                        <Badge key={idx} variant="outline" className="text-[10px] font-medium border-primary/20 text-primary/70 rounded-lg">
                                            #{kw}
                                        </Badge>
                                    ))}
                                </div>
                            </CardContent>

                            <CardFooter className="px-5 pb-5 pt-0 gap-3">
                                <Button
                                    className="flex-1 rounded-2xl font-bold bg-accent hover:bg-accent/80 text-foreground border-none transition-all"
                                    variant="outline"
                                    size="sm"
                                >
                                    상세 편집
                                </Button>
                                <Button
                                    className={cn(
                                        "flex-1 rounded-2xl font-bold transition-all shadow-lg",
                                        item.processing_status === "COMPLETED"
                                            ? "bg-emerald-500 hover:bg-emerald-600 shadow-emerald-500/20"
                                            : "shadow-primary/20"
                                    )}
                                    size="sm"
                                    onClick={() => handleProcess(item.id)}
                                    disabled={processingIds.has(item.id) || item.processing_status === "PROCESSING"}
                                >
                                    {processingIds.has(item.id) ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : item.processing_status === "COMPLETED" ? (
                                        "재가공"
                                    ) : (
                                        "가공 시작"
                                    )}
                                </Button>
                            </CardFooter>
                        </Card>
                    ))
                )}
            </div>
        </div>
    );
}
