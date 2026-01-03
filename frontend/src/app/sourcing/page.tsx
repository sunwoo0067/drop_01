"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { Search, Filter, Plus, Loader2, ExternalLink, Info } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Drawer } from "@/components/ui/Drawer";
import api from "@/lib/api";
import { SourcingCandidate } from "@/types";

export default function SourcingPage() {
    const [searchTerm, setSearchTerm] = useState("");
    const [items, setItems] = useState<SourcingCandidate[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [promotingIds, setPromotingIds] = useState<Set<string>>(new Set());
    const [selectedItem, setSelectedItem] = useState<SourcingCandidate | null>(null);

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
            await api.patch(`/sourcing/candidates/${candidateId}`, { status: "APPROVED" });
            await api.post(`/sourcing/candidates/${candidateId}/promote`, {
                autoProcess: true,
                minImagesRequired: 1
            });
            setItems(prev => prev.filter(item => item.id !== candidateId));
            if (selectedItem?.id === candidateId) setSelectedItem(null);
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
        <div className="space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 px-3 py-2 border border-border bg-card rounded-sm">
                <h1 className="text-sm font-semibold">상품 소싱</h1>
                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm">
                        <Filter className="mr-1.5 h-3 w-3" />
                        필터
                    </Button>
                    <Button size="sm">
                        <Plus className="mr-1.5 h-3 w-3" />
                        새 소싱 작업
                    </Button>
                </div>
            </div>

            <Card className="border-none bg-muted/20">
                <CardContent className="p-3">
                    <div className="flex gap-2">
                        <Input
                            placeholder="키워드 또는 상품 ID 검색..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="max-w-md bg-background"
                            size="sm"
                        />
                        <Button size="sm" onClick={handleSearch} disabled={loading}>
                            <Search className="mr-1.5 h-3 w-3" />
                            검색
                        </Button>
                    </div>
                </CardContent>
            </Card>

            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
                {loading ? (
                    <div className="col-span-full h-80 flex flex-col items-center justify-center space-y-4">
                        <Loader2 className="h-10 w-10 animate-spin text-primary" />
                        <p className="text-muted-foreground animate-pulse text-xs">데이터 로드 중...</p>
                    </div>
                ) : error ? (
                    <div className="col-span-full h-80 flex items-center justify-center text-destructive bg-destructive/5 rounded-sm border border-destructive/20 text-xs">
                        {error}
                    </div>
                ) : items.length === 0 ? (
                    <div className="col-span-full h-80 flex flex-col items-center justify-center text-muted-foreground bg-muted/30 rounded-sm border border-dashed">
                        <Search className="h-10 w-10 mb-2 opacity-20" />
                        <p className="text-xs">소싱 후보가 없습니다.</p>
                    </div>
                ) : (
                    items.map((item) => {
                        const margin = item.marginScore ? (item.marginScore * 100).toFixed(1) : "0.0";
                        const isHighMargin = item.marginScore && item.marginScore >= 0.2;

                        return (
                            <Card key={item.id} className="group overflow-hidden border border-border/50 bg-card hover:border-primary/50 transition-all duration-200">
                                <div className="aspect-square relative overflow-hidden bg-muted cursor-pointer" onClick={() => setSelectedItem(item)}>
                                    {item.thumbnailUrl ? (
                                        <Image
                                            src={item.thumbnailUrl}
                                            alt={item.name || ""}
                                            fill
                                            sizes="200px"
                                            className="object-cover transition-transform duration-500 group-hover:scale-105"
                                        />
                                    ) : (
                                        <div className="w-full h-full flex items-center justify-center text-muted-foreground/30">
                                            <Search className="h-8 w-8" />
                                        </div>
                                    )}
                                    <div className="absolute top-1.5 left-1.5 flex gap-1">
                                        <Badge className="bg-black/60 backdrop-blur-sm border-none text-[9px] px-1 py-0 h-4 text-white">
                                            {item.supplierCode.toUpperCase()}
                                        </Badge>
                                    </div>
                                    {isHighMargin && (
                                        <div className="absolute top-1.5 right-1.5">
                                            <div className="bg-emerald-500 size-2 rounded-full animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
                                        </div>
                                    )}
                                </div>
                                <CardContent className="p-2 space-y-1">
                                    <h3
                                        className="text-[11px] font-semibold leading-tight line-clamp-2 min-h-[2.2em] cursor-pointer hover:text-primary transition-colors"
                                        onClick={() => setSelectedItem(item)}
                                    >
                                        {item.name}
                                    </h3>
                                    <div className="flex items-center justify-between">
                                        <p className="text-xs font-black">{item.supplyPrice?.toLocaleString()}<span className="text-[10px] font-normal ml-0.5">원</span></p>
                                        <p className={`text-[10px] font-bold ${isHighMargin ? 'text-emerald-500' : 'text-blue-500'}`}>
                                            {margin}%
                                        </p>
                                    </div>
                                    <div className="flex gap-1 pt-0.5">
                                        <Badge variant="outline" className="text-[8px] px-1 py-0 h-3.5 border-muted text-muted-foreground uppercase">
                                            {item.sourceStrategy}
                                        </Badge>
                                    </div>
                                </CardContent>
                                <CardFooter className="p-2 pt-0 grid grid-cols-2 gap-1.5">
                                    <Button
                                        variant="ghost"
                                        size="xs"
                                        className="h-7 text-[10px] bg-muted/50 hover:bg-muted font-medium"
                                        onClick={() => setSelectedItem(item)}
                                    >
                                        상세
                                    </Button>
                                    <Button
                                        variant="primary"
                                        size="xs"
                                        className="h-7 text-[10px] font-bold"
                                        onClick={() => handlePromote(item.id)}
                                        disabled={promotingIds.has(item.id)}
                                    >
                                        {promotingIds.has(item.id) ? (
                                            <Loader2 className="h-3 w-3 animate-spin" />
                                        ) : (
                                            "승인"
                                        )}
                                    </Button>
                                </CardFooter>
                            </Card>
                        );
                    })
                )}
            </div>

            {/* Sourcing Detail Drawer */}
            <Drawer
                isOpen={!!selectedItem}
                onClose={() => setSelectedItem(null)}
                title="소싱 후보 상세"
                description={selectedItem?.name || ""}
                size="lg"
                footer={
                    <div className="flex justify-end gap-2">
                        <Button variant="outline" size="sm" onClick={() => setSelectedItem(null)}>
                            닫기
                        </Button>
                        <Button
                            variant="primary"
                            size="sm"
                            onClick={() => selectedItem && handlePromote(selectedItem.id)}
                            disabled={!selectedItem || promotingIds.has(selectedItem.id)}
                        >
                            {selectedItem && promotingIds.has(selectedItem.id) ? (
                                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                            ) : null}
                            소싱 승인 (가공 시작)
                        </Button>
                    </div>
                }
            >
                {selectedItem && (
                    <div className="space-y-6">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="aspect-square relative rounded-xl border border-border overflow-hidden bg-muted">
                                {selectedItem.thumbnailUrl ? (
                                    <Image
                                        src={selectedItem.thumbnailUrl}
                                        alt={selectedItem.name || ""}
                                        fill
                                        className="object-contain"
                                    />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center">
                                        <Search className="h-16 w-16 text-muted-foreground/20" />
                                    </div>
                                )}
                            </div>
                            <div className="space-y-5">
                                <div className="space-y-1.5">
                                    <div className="flex gap-1.5">
                                        <Badge variant="primary" className="text-[10px]">{selectedItem.supplierCode.toUpperCase()}</Badge>
                                        <Badge variant="outline" className="text-[10px]">{selectedItem.sourceStrategy}</Badge>
                                    </div>
                                    <h3 className="text-xl font-bold leading-tight">{selectedItem.name}</h3>
                                    <p className="text-xs text-muted-foreground font-mono">{selectedItem.supplierItemId}</p>
                                </div>

                                <div className="grid grid-cols-2 gap-4 border-y border-border/50 py-4">
                                    <div className="space-y-0.5">
                                        <p className="text-[10px] font-bold text-muted-foreground uppercase">공급가</p>
                                        <p className="text-2xl font-black">{selectedItem.supplyPrice?.toLocaleString()}<span className="text-sm font-normal ml-0.5">원</span></p>
                                    </div>
                                    <div className="space-y-0.5">
                                        <p className="text-[10px] font-bold text-muted-foreground uppercase">분석 수익률</p>
                                        <p className={`text-2xl font-black ${selectedItem.marginScore && selectedItem.marginScore >= 0.2 ? 'text-emerald-500' : 'text-blue-500'}`}>
                                            {(selectedItem.marginScore ? selectedItem.marginScore * 100 : 0.0).toFixed(1)}%
                                        </p>
                                    </div>
                                </div>

                                <div className="space-y-4">
                                    <div className="flex items-center justify-between text-sm">
                                        <span className="text-muted-foreground">현재 상태</span>
                                        <Badge
                                            variant={selectedItem.status === 'PENDING' ? 'warning' : selectedItem.status === 'APPROVED' ? 'success' : 'secondary'}
                                            className="font-bold"
                                        >
                                            {selectedItem.status}
                                        </Badge>
                                    </div>
                                    <div className="flex items-center justify-between text-sm">
                                        <span className="text-muted-foreground">가격 경쟁력</span>
                                        <span className="font-semibold text-emerald-500">상위 5%</span>
                                    </div>
                                    <div className="flex items-center justify-between text-sm">
                                        <span className="text-muted-foreground">수집 일시</span>
                                        <span className="font-medium">{new Date(selectedItem.createdAt).toLocaleDateString()}</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className="space-y-3">
                            <h4 className="text-xs font-bold text-muted-foreground uppercase flex items-center gap-1.5">
                                <Info className="h-3.5 w-3.5" />
                                상품 가이드라인 및 전략
                            </h4>
                            <div className="rounded-lg bg-muted/30 p-4 border border-border/50 text-sm space-y-2 text-muted-foreground leading-relaxed">
                                <p>• 이 상품은 <strong>{selectedItem.sourceStrategy}</strong> 전략에 의해 발굴되었습니다.</p>
                                <p>• 공급가 {selectedItem.supplyPrice?.toLocaleString()}원 기준, 시장 평균 판매가는 약 {(selectedItem.supplyPrice ? selectedItem.supplyPrice * 1.3 : 0).toLocaleString()}원으로 예상됩니다.</p>
                                <p>• 승인 시 AI 에이전트가 즉시 {selectedItem.supplierCode === 'ownerclan' ? '오너클랜' : '공급사'} 데이터를 기반으로 가공을 시작합니다.</p>
                            </div>
                        </div>
                    </div>
                )}
            </Drawer>
        </div>
    );
}
