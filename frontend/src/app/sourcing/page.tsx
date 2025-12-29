"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { Search, Filter, Plus } from "lucide-react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import api from "@/lib/api";
import { SourcingCandidate } from "@/types";

export default function SourcingPage() {
    const [searchTerm, setSearchTerm] = useState("");
    const [items, setItems] = useState<SourcingCandidate[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [promotingIds, setPromotingIds] = useState<Set<string>>(new Set());

    const fetchCandidates = async (q?: string) => {
        setLoading(true);
        setError(null);
        try {
            const response = await api.get("/sourcing/candidates", {
                params: {
                    q: (q ?? "").trim() || undefined,
                    limit: 50,
                    offset: 0,
                },
            });
            setItems(Array.isArray(response.data) ? response.data : []);
        } catch (e) {
            console.error("Failed to fetch sourcing candidates", e);
            setError("소싱 후보 목록을 불러오지 못했습니다.");
            setItems([]);
        } finally {
            setLoading(false);
        }
    };

    const handlePromote = async (candidateId: string) => {
        if (promotingIds.has(candidateId)) return;

        setPromotingIds(prev => new Set(prev).add(candidateId));
        try {
            // 1. Mark as APPROVED
            await api.patch(`/sourcing/candidates/${candidateId}`, { status: "APPROVED" });

            // 2. Promote to Product
            await api.post(`/sourcing/candidates/${candidateId}/promote`, {
                autoProcess: true,
                minImagesRequired: 1
            });

            // 3. Remove from list or refresh
            setItems(prev => prev.filter(item => item.id !== candidateId));
        } catch (e) {
            console.error("Promotion failed", e);
            alert("상품 승격에 실패했습니다.");
        } finally {
            setPromotingIds(prev => {
                const next = new Set(prev);
                next.delete(candidateId);
                return next;
            });
        }
    };

    useEffect(() => {
        fetchCandidates();
    }, []);

    const handleSearch = async () => {
        await fetchCandidates(searchTerm);
    };

    return (
        <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <h1 className="text-3xl font-bold tracking-tight">상품 소싱</h1>
                <div className="flex items-center gap-2">
                    <Button variant="outline">
                        <Filter className="mr-2 h-4 w-4" />
                        필터
                    </Button>
                    <Button>
                        <Plus className="mr-2 h-4 w-4" />
                        새 소싱 작업
                    </Button>
                </div>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>상품 검색</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex gap-4">
                        <Input
                            placeholder="키워드 또는 상품 ID 검색..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="max-w-md"
                        />
                        <Button onClick={handleSearch} disabled={loading}>
                            <Search className="mr-2 h-4 w-4" />
                            검색
                        </Button>
                    </div>
                </CardContent>
            </Card>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {loading ? (
                    <div className="col-span-full h-80 flex flex-col items-center justify-center space-y-4">
                        <Loader2 className="h-10 w-10 animate-spin text-primary" />
                        <p className="text-muted-foreground animate-pulse">상품 데이터를 불러오는 중...</p>
                    </div>
                ) : error ? (
                    <div className="col-span-full h-80 flex items-center justify-center text-destructive bg-destructive/5 rounded-xl border border-destructive/20">
                        {error}
                    </div>
                ) : items.length === 0 ? (
                    <div className="col-span-full h-80 flex flex-col items-center justify-center text-muted-foreground bg-muted/30 rounded-xl border border-dashed">
                        <Search className="h-12 w-12 mb-4 opacity-20" />
                        <p>소싱 후보가 없습니다.</p>
                    </div>
                ) : (
                    items.map((item) => {
                        const margin = item.marginScore ? (item.marginScore * 100).toFixed(1) : "0.0";
                        const isHighMargin = item.marginScore && item.marginScore >= 0.2;

                        return (
                            <Card key={item.id} className="group overflow-hidden border-none shadow-md hover:shadow-xl transition-all duration-300 hover:-translate-y-1 bg-card/50 backdrop-blur-sm">
                                <div className="aspect-[4/3] relative overflow-hidden bg-muted">
                                    {item.thumbnailUrl ? (
                                        <Image
                                            src={item.thumbnailUrl}
                                            alt={item.name || "상품 이미지"}
                                            fill
                                            sizes="(min-width: 1024px) 25vw, (min-width: 768px) 33vw, 100vw"
                                            className="object-cover transition-transform duration-500 group-hover:scale-110"
                                        />
                                    ) : (
                                        <div className="w-full h-full flex items-center justify-center text-muted-foreground/30">
                                            <Search className="h-12 w-12" />
                                        </div>
                                    )}
                                    <div className="absolute top-2 left-2 flex gap-1">
                                        <Badge className="bg-black/50 backdrop-blur-md border-none text-white hover:bg-black/60">
                                            {item.supplierCode.toUpperCase()}
                                        </Badge>
                                        {isHighMargin && (
                                            <Badge className="bg-emerald-500/80 backdrop-blur-md border-none text-white">
                                                고수익
                                            </Badge>
                                        )}
                                    </div>
                                    <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-end p-4">
                                        <p className="text-white text-xs font-medium line-clamp-2">{item.name}</p>
                                    </div>
                                </div>
                                <CardContent className="p-5 space-y-3">
                                    <h3 className="font-bold text-lg leading-tight line-clamp-1 group-hover:text-primary transition-colors">
                                        {item.name}
                                    </h3>
                                    <div className="flex items-baseline justify-between">
                                        <div className="space-y-0.5">
                                            <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">공급가</p>
                                            <p className="text-xl font-black">{item.supplyPrice?.toLocaleString()}<span className="text-sm font-normal ml-0.5">원</span></p>
                                        </div>
                                        <div className="text-right space-y-0.5">
                                            <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">수익률</p>
                                            <p className={`text-lg font-bold ${isHighMargin ? 'text-emerald-500' : 'text-blue-500'}`}>
                                                {margin}%
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex flex-wrap gap-1.5 pt-1">
                                        <Badge variant="secondary" className="text-[10px] uppercase font-bold tracking-tighter px-1.5 py-0">
                                            {item.sourceStrategy}
                                        </Badge>
                                        <Badge
                                            variant="outline"
                                            className={`text-[10px] uppercase font-bold tracking-tighter px-1.5 py-0 ${item.status === 'PENDING' ? 'border-yellow-500/50 text-yellow-600 bg-yellow-50' :
                                                item.status === 'APPROVED' ? 'border-emerald-500/50 text-emerald-600 bg-emerald-50' :
                                                    'border-muted text-muted-foreground'
                                                }`}
                                        >
                                            {item.status}
                                        </Badge>
                                    </div>
                                </CardContent>
                                <CardFooter className="px-5 pb-5 pt-0 grid grid-cols-2 gap-2">
                                    <Button className="w-full bg-primary/10 hover:bg-primary/20 text-primary border-none" variant="outline" size="sm">
                                        상세 정보
                                    </Button>
                                    <Button
                                        className="flex-1 rounded-xl"
                                        variant="primary"
                                        size="sm"
                                        onClick={() => handlePromote(item.id)}
                                        disabled={promotingIds.has(item.id)}
                                    >
                                        {promotingIds.has(item.id) ? (
                                            <Loader2 className="h-4 w-4 animate-spin" />
                                        ) : (
                                            "소싱 승인"
                                        )}
                                    </Button>
                                </CardFooter>
                            </Card>
                        );
                    })
                )}
            </div>
        </div>
    );
}
