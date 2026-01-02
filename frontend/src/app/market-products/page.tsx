"use client";

import { useState, useMemo, useCallback } from "react";
import useSWR from 'swr';
import {
    Search,
    ShoppingBag,
    RotateCw,
    AlertCircle,
    CheckCircle2,
    ArrowLeft
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import api from "@/lib/api";
import { Select } from "@/components/ui/Select";
import MarketProductCard from "@/components/MarketProductCard";

const fetcher = (url: string) => api.get(url).then(res => res.data);

export default function MarketProductsPage() {
    const [selectedAccountId, setSelectedAccountId] = useState<string>("all");
    const [searchTerm, setSearchTerm] = useState("");

    // SWR로 계정 데이터 가져오기
    const { data: accountsData } = useSWR(
        ['/settings/markets/coupang/accounts', '/settings/markets/smartstore/accounts'],
        async (urls) => {
            const [coupangRes, smartstoreRes] = await Promise.all(
                urls.map(url => api.get(url))
            );

            const coupangAccounts = (coupangRes.data || []).map((acc: any) => ({
                id: acc.id,
                name: acc.name || `쿠팡-${acc.vendorId}`,
                marketCode: "COUPANG"
            }));

            const smartstoreAccounts = (smartstoreRes.data || []).map((acc: any) => ({
                id: acc.id,
                name: acc.name || `스토어-${acc.id.substring(0, 4)}`,
                marketCode: "SMARTSTORE"
            }));

            return [...coupangAccounts, ...smartstoreAccounts];
        },
        { revalidateOnFocus: false, revalidateOnReconnect: false }
    );

    const accounts = accountsData || [];

    // SWR로 상품 데이터 가져오기 - 캐싱 및 자동 재검증
    const productsUrl = selectedAccountId && selectedAccountId !== 'all'
        ? `/market/products?accountId=${selectedAccountId}&limit=100`
        : '/market/products?marketCode=ALL&limit=100';

    const { data: productsData, error: productsError, isLoading, mutate } = useSWR(
        productsUrl,
        fetcher,
        {
            revalidateOnFocus: false,
            revalidateOnReconnect: false,
            dedupingInterval: 60000, // 60초 동안 중복 요청 방지
        }
    );

    const items = useMemo(() => productsData?.items ?? [], [productsData]);
    const total = productsData?.total || 0;
    const error = productsError ? "마켓 상품 목록을 불러오지 못했습니다." : null;

    const handleAccountChange = useCallback((value: string) => {
        setSelectedAccountId(value);
    }, []);

    const handleViewExternal = useCallback((item: any) => {
        if (item.storeUrl) {
            window.open(item.storeUrl, '_blank');
            return;
        }
        if (item.marketCode === "COUPANG") {
            window.open(`https://wing.coupang.com/product/${item.marketItemId}`, '_blank');
            return;
        }
        if (item.marketCode === "SMARTSTORE") {
            window.open("https://sell.smartstore.naver.com/#/products", "_blank");
        }
    }, []);

    const handlePremiumOptimize = useCallback(async (productId: string) => {
        try {
            await api.post(`/products/${productId}/premium-optimize`);
            // SWR mutate로 데이터 갱신 (캐시 무시하고 즉시 재요청)
            await mutate();
            alert("프리미엄 고도화 작업이 시작되었습니다. 결과는 잠시 후 확인하실 수 있습니다.");
        } catch (e) {
            console.error("Failed to trigger premium optimize", e);
            alert("작업 요청에 실패했습니다.");
        }
    }, [mutate]);

    const filteredItems = useMemo(() => {
        const searchLower = searchTerm.toLowerCase();
        return items.filter((item: any) =>
            (item.name || "").toLowerCase().includes(searchLower) ||
            (item.processedName || "").toLowerCase().includes(searchLower) ||
            (item.marketItemId || "").toString().toLowerCase().includes(searchLower)
        );
    }, [items, searchTerm]);

    return (
        <div className="space-y-4 animate-in fade-in duration-500">
            {/* 헤더 섹션 */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 px-3 py-2 border border-border bg-card rounded-sm">
                <div className="flex items-center gap-3">
                    <div className="h-6 w-6 rounded-sm bg-primary/10 flex items-center justify-center">
                        <ShoppingBag className="h-3 w-3 text-primary" />
                    </div>
                    <div>
                        <h1 className="text-sm font-semibold text-foreground">마켓 상품</h1>
                        <p className="text-[10px] text-muted-foreground">등록 상품 관리 및 상태 확인</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => window.location.href = '/registration'}
                    >
                        <ArrowLeft className="mr-1.5 h-3 w-3" />
                        등록 페이지
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => mutate()}>
                        <RotateCw className="mr-1.5 h-3 w-3" />
                        새로고침
                    </Button>
                </div>
            </div>

            {/* 통계 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Card className="border border-border">
                    <CardContent className="p-3">
                        <div className="flex items-center gap-3">
                            <div className="h-7 w-7 rounded-sm bg-muted flex items-center justify-center">
                                <ShoppingBag className="h-3.5 w-3.5 text-muted-foreground" />
                            </div>
                            <div>
                                <p className="text-[10px] text-muted-foreground">등록된 상품</p>
                                <p className="text-lg font-semibold">{total}</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
                <Card className="border border-border">
                    <CardContent className="p-3">
                        <div className="flex items-center gap-3">
                            <div className="h-7 w-7 rounded-sm bg-muted flex items-center justify-center">
                                <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                            </div>
                            <div>
                                <p className="text-[10px] text-muted-foreground">활성 상품</p>
                                <p className="text-lg font-semibold">{items.filter((i: any) => i.status === "ACTIVE").length}</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* 필터 및 검색 */}
            <div className="flex flex-col md:flex-row gap-3 items-center">
                <div className="w-full md:w-64">
                    <Select
                        value={selectedAccountId}
                        options={[
                            { value: 'all', label: '모든 계정 보기' },
                            ...accounts.map((acc: any) => ({
                                value: acc.id,
                                label: `${acc.marketCode.toUpperCase()} - ${acc.name}`
                            }))
                        ]}
                        onChange={(e) => handleAccountChange(e.target.value)}
                        className="bg-accent/50 border-none"
                    />
                </div>
                <div className="relative flex-1 group w-full">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
                    <Input
                        placeholder="상품명 또는 상품 ID로 검색..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="pl-9"
                        size="sm"
                    />
                </div>
            </div>

            {/* 상품 목록 */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {isLoading ? (
                    <div className="col-span-full h-80 flex flex-col items-center justify-center space-y-4">
                        <div className="h-12 w-12 rounded-full border-4 border-primary/20 border-t-primary animate-spin" />
                        <p className="text-muted-foreground font-medium animate-pulse">마켓 상품을 불러오는 중...</p>
                    </div>
                ) : error ? (
                    <Card className="col-span-full border-2 border-destructive/20 bg-destructive/5">
                        <CardContent className="flex flex-col items-center py-12 text-center">
                            <AlertCircle className="h-12 w-12 text-destructive mb-4" />
                            <h3 className="text-xl font-bold mb-2">오류 발생</h3>
                            <p className="text-muted-foreground">{error}</p>
                            <Button className="mt-6 rounded-xl" variant="outline" onClick={() => mutate()}>다시 시도</Button>
                        </CardContent>
                    </Card>
                ) : filteredItems.length === 0 ? (
                    <div className="col-span-full py-20 text-center">
                        <div className="h-20 w-20 bg-accent rounded-full flex items-center justify-center mx-auto mb-6">
                            <ShoppingBag className="h-10 w-10 text-muted-foreground/50" />
                        </div>
                        <h3 className="text-2xl font-bold text-foreground mb-2">등록된 상품이 없습니다</h3>
                        <p className="text-muted-foreground">상품 등록 페이지에서 상품을 쿠팡에 등록해 주세요.</p>
                        <Button className="mt-8 rounded-xl h-11 px-8" onClick={() => window.location.href = '/registration'}>
                            상품 등록하러 가기
                        </Button>
                    </div>
                ) : (
                    filteredItems.map((item: any) => (
                        <MarketProductCard
                            key={item.id}
                            item={item}
                            onViewExternal={handleViewExternal}
                            onPremiumOptimize={handlePremiumOptimize}
                        />
                    ))
                )}
            </div>
        </div>
    );
}
