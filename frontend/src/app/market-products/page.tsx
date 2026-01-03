"use client";

import { useState, useMemo, useCallback } from "react";
import useSWR from 'swr';
import Image from "next/image";
import {
    Search,
    ShoppingBag,
    RotateCw,
    AlertCircle,
    CheckCircle2,
    ArrowLeft,
    ExternalLink,
    Zap,
    Sparkles,
    Image as ImageIcon,
    Calendar,
    ArrowUpRight,
    TrendingUp,
    Loader2
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Table, TableColumn } from "@/components/ui/Table";
import { Drawer } from "@/components/ui/Drawer";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import api from "@/lib/api";
import { Select } from "@/components/ui/Select";
import { cn } from "@/lib/utils";

const fetcher = (url: string) => api.get(url).then(res => res.data);

interface MarketProduct {
    id: string;
    productId: string;
    marketItemId: string;
    status: string;
    linkedAt: string | null;
    name: string | null;
    processedName: string | null;
    sellingPrice: number;
    processedImageUrls: string[] | null;
    productStatus: string | null;
    processingStatus: string | null;
    marketAccountId: string;
    accountName: string | null;
    marketCode: string;
    storeUrl?: string | null;
}

export default function MarketProductsPage() {
    const [selectedAccountId, setSelectedAccountId] = useState<string>("all");
    const [searchTerm, setSearchTerm] = useState("");
    const [selectedItem, setSelectedItem] = useState<MarketProduct | null>(null);

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

    // SWR로 상품 데이터 가져오기
    const productsUrl = selectedAccountId && selectedAccountId !== 'all'
        ? `/market/products?accountId=${selectedAccountId}&limit=100`
        : '/market/products?marketCode=ALL&limit=100';

    const { data: productsData, error: productsError, isLoading, mutate } = useSWR(
        productsUrl,
        fetcher,
        {
            revalidateOnFocus: false,
            revalidateOnReconnect: false,
            dedupingInterval: 60000,
        }
    );

    const items = useMemo(() => productsData?.items ?? [], [productsData]);
    const total = productsData?.total || 0;
    const error = productsError ? "마켓 상품 목록을 불러오지 못했습니다." : null;

    const handleAccountChange = useCallback((value: string) => {
        setSelectedAccountId(value);
    }, []);

    const handleViewExternal = useCallback((item: MarketProduct) => {
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
            await mutate();
            alert("프리미엄 고도화 작업이 시작되었습니다. 결과는 잠시 후 확인하실 수 있습니다.");
        } catch (e) {
            console.error("Failed to trigger premium optimize", e);
            alert("작업 요청에 실패했습니다.");
        }
    }, [mutate]);

    const filteredItems = useMemo(() => {
        const searchLower = searchTerm.toLowerCase();
        return items.filter((item: MarketProduct) =>
            (item.name || "").toLowerCase().includes(searchLower) ||
            (item.processedName || "").toLowerCase().includes(searchLower) ||
            (item.marketItemId || "").toString().toLowerCase().includes(searchLower)
        );
    }, [items, searchTerm]);

    const formatDate = (dateStr: string | null) => {
        if (!dateStr) return "-";
        return new Date(dateStr).toLocaleDateString('ko-KR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
        });
    };

    const columns: TableColumn<MarketProduct>[] = [
        {
            key: "image",
            title: "이미지",
            width: "80px",
            render: (_, row) => (
                <div className="h-10 w-10 rounded-lg overflow-hidden bg-muted relative">
                    {row.processedImageUrls && row.processedImageUrls.length > 0 ? (
                        <Image src={row.processedImageUrls[0]} alt={row.name || ""} fill className="object-cover" />
                    ) : (
                        <ImageIcon className="h-4 w-4 m-auto absolute inset-0 text-muted-foreground/30" />
                    )}
                </div>
            )
        },
        {
            key: "name",
            title: "상품 정보",
            render: (_, row) => (
                <div className="flex flex-col max-w-[400px]">
                    <span className="font-bold truncate text-foreground/90">{row.processedName || row.name || "상품명 없음"}</span>
                    <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded uppercase font-black tracking-widest">{row.marketCode}</span>
                        <span className="text-[10px] text-muted-foreground/60 font-mono">ID: {row.marketItemId}</span>
                    </div>
                </div>
            )
        },
        {
            key: "accountName",
            title: "마켓 계정",
            width: "140px",
            render: (name, row) => (
                <Badge variant="outline" className={cn(
                    "font-bold text-[10px] h-5",
                    row.marketCode === "COUPANG" ? "bg-orange-500/5 text-orange-600 border-orange-200" : "bg-emerald-500/5 text-emerald-600 border-emerald-200"
                )}>
                    {name || (row.marketCode === "COUPANG" ? "쿠팡" : "스토어")}
                </Badge>
            )
        },
        {
            key: "status",
            title: "매칭 상태",
            width: "100px",
            render: (status) => (
                <Badge variant={status === "ACTIVE" ? "success" : "outline"} className="text-[10px] h-5">
                    {status === "ACTIVE" ? "매칭됨" : status}
                </Badge>
            )
        },
        {
            key: "sellingPrice",
            title: "판매가",
            width: "120px",
            align: "right",
            render: (price) => <span className="font-mono font-bold text-primary">{Number(price || 0).toLocaleString()}원</span>
        },
        {
            key: "linkedAt",
            title: "등록일",
            width: "100px",
            align: "right",
            render: (date) => <span className="text-[11px] text-muted-foreground font-medium">{formatDate(date)}</span>
        },
        {
            key: "actions",
            title: "작업",
            width: "120px",
            align: "right",
            render: (_, row) => {
                const isOptimizing = row.processingStatus === "PROCESSING";
                return (
                    <div className="flex items-center justify-end gap-1">
                        <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8 rounded-lg text-muted-foreground hover:text-primary transition-colors"
                            onClick={(e) => {
                                e.stopPropagation();
                                handleViewExternal(row);
                            }}
                        >
                            <ExternalLink className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                            size="icon"
                            variant="ghost"
                            className={cn(
                                "h-8 w-8 rounded-lg transition-colors",
                                isOptimizing ? "text-amber-500 animate-pulse" : "text-muted-foreground hover:text-emerald-500"
                            )}
                            disabled={isOptimizing}
                            onClick={(e) => {
                                e.stopPropagation();
                                handlePremiumOptimize(row.productId);
                            }}
                        >
                            {isOptimizing ? <Zap className="h-3.5 w-3.5" /> : <Sparkles className="h-3.5 w-3.5" />}
                        </Button>
                    </div>
                );
            }
        }
    ];

    return (
        <div className="space-y-4 animate-in fade-in duration-500 pb-10">
            {/* Header Section */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 px-3 py-2 border border-border bg-card/50 backdrop-blur-sm rounded-sm text-sm">
                <Breadcrumb items={[{ label: "마켓 상품 관리", icon: <ShoppingBag className="h-3 w-3" /> }]} />
                <div className="flex items-center gap-2">
                    <Button
                        variant="ghost"
                        size="sm"
                        className="text-[11px] font-bold h-8 px-3"
                        onClick={() => window.location.href = '/registration'}
                    >
                        <ArrowLeft className="mr-1.5 h-3 w-3" />
                        등록 센터로 후퇴
                    </Button>
                    <div className="h-4 w-px bg-border mx-1" />
                    <Button variant="outline" size="sm" onClick={() => mutate()} className="h-8 rounded-lg px-3 font-bold border-border/50 bg-background/50">
                        <RotateCw className="mr-1.5 h-3 w-3" />
                        동기화
                    </Button>
                </div>
            </div>

            {/* Stats Overview */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {[
                    { label: "총 마켓 상품", value: total, icon: ShoppingBag, color: "text-primary" },
                    { label: "매칭된 상품", value: items.filter(i => i.status === "ACTIVE").length, icon: CheckCircle2, color: "text-emerald-500" },
                    { label: "미매칭/비활성", value: items.length - items.filter(i => i.status === "ACTIVE").length, icon: AlertCircle, color: "text-amber-500" },
                    { label: "검색 결과", value: filteredItems.length, icon: TrendingUp, color: "text-blue-500" }
                ].map((stat, idx) => (
                    <Card key={idx} className="bg-card/40 border border-border pb-3 pt-4 px-4 shadow-sm relative overflow-hidden group">
                        <stat.icon className={cn("absolute -right-2 -bottom-2 h-12 w-12 opacity-5 group-hover:scale-110 transition-transform", stat.color)} />
                        <p className="text-[10px] font-black text-muted-foreground uppercase tracking-widest">{stat.label}</p>
                        <p className={cn("text-2xl font-black mt-1", stat.color)}>{stat.value}</p>
                    </Card>
                ))}
            </div>

            {/* Toolbar */}
            <div className="flex flex-col md:flex-row items-stretch md:items-center gap-3 bg-card border border-border p-2 rounded-sm pr-4 shadow-sm">
                <div className="w-full md:w-64 relative group">
                    <Select
                        value={selectedAccountId}
                        options={[
                            { value: 'all', label: '모든 마켓 계정' },
                            ...accounts.map((acc: any) => ({
                                value: acc.id,
                                label: `${acc.marketCode}: ${acc.name}`
                            }))
                        ]}
                        onChange={(e) => handleAccountChange(e.target.value)}
                        className="bg-accent/40 border-none h-10 font-bold text-xs"
                    />
                </div>
                <div className="h-6 w-px bg-border hidden md:block mx-1" />
                <div className="relative flex-1 group">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
                    <Input
                        placeholder="상품명 또는 마켓 ID로 필터링..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="pl-10 h-10 bg-transparent border-none focus-visible:ring-0 focus-visible:ring-offset-0 text-sm font-medium"
                    />
                </div>
            </div>

            {/* Table */}
            <div className="border border-border/50 rounded-sm bg-card shadow-sm overflow-hidden min-h-[400px]">
                <Table
                    columns={columns}
                    data={filteredItems}
                    loading={isLoading}
                    hover
                    onRowClick={(row) => setSelectedItem(row)}
                    emptyMessage="관리 중인 마켓 상품이 없습니다."
                />
            </div>

            {/* Detail Drawer */}
            <Drawer
                isOpen={!!selectedItem}
                onClose={() => setSelectedItem(null)}
                title="마켓 상품 정보"
                description="마켓 등록 데이터 및 내부 매칭 상태를 확인합니다."
                size="lg"
                footer={
                    <div className="flex items-center justify-between w-full">
                        <Button
                            variant="outline"
                            className="rounded-xl font-bold h-11"
                            onClick={() => selectedItem && handleViewExternal(selectedItem)}
                        >
                            <ExternalLink className="mr-2 h-4 w-4" />
                            마켓에서 보기
                        </Button>
                        <div className="flex items-center gap-2">
                            <Button variant="outline" onClick={() => setSelectedItem(null)} className="rounded-xl font-bold h-11 px-6">
                                닫기
                            </Button>
                            <Button
                                className="rounded-xl font-black h-11 px-8 shadow-lg shadow-emerald-500/20 bg-emerald-500 hover:bg-emerald-600"
                                onClick={() => selectedItem && handlePremiumOptimize(selectedItem.productId)}
                                disabled={selectedItem?.processingStatus === "PROCESSING"}
                            >
                                {selectedItem?.processingStatus === "PROCESSING" ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <Sparkles className="mr-2 h-4 w-4" />
                                )}
                                프리미엄 고도화 실행
                            </Button>
                        </div>
                    </div>
                }
            >
                {selectedItem && (
                    <div className="space-y-8 pb-10">
                        {/* Summary Card */}
                        <div className="p-6 rounded-3xl bg-gradient-to-br from-primary/10 via-primary/5 to-background border border-primary/10 flex flex-col items-center text-center space-y-4">
                            <div className="h-16 w-16 rounded-[2rem] bg-white shadow-xl flex items-center justify-center p-1 border border-primary/20">
                                {selectedItem.processedImageUrls?.[0] ? (
                                    <Image src={selectedItem.processedImageUrls[0]} alt="img" width={60} height={60} className="object-cover rounded-[1.8rem]" />
                                ) : <ShoppingBag className="h-8 w-8 text-primary/40" />}
                            </div>
                            <div className="space-y-1">
                                <h3 className="text-xl font-black tracking-tight">{selectedItem.processedName || selectedItem.name}</h3>
                                <p className="text-[10px] font-black text-muted-foreground uppercase tracking-widest">{selectedItem.marketCode} LIVE PRODUCT</p>
                            </div>
                            <Badge variant="success" className="px-4 py-1.5 rounded-full text-xs font-bold shadow-sm">
                                {selectedItem.status === "ACTIVE" ? "마켓 매칭 활성" : selectedItem.status}
                            </Badge>
                        </div>

                        {/* Details Grid */}
                        <div className="grid grid-cols-2 gap-4">
                            {[
                                { label: "마켓 상품 ID", value: selectedItem.marketItemId, icon: ShoppingBag },
                                { label: "내부 상품 ID", value: selectedItem.productId, icon: Calendar },
                                { label: "마켓 계정", value: selectedItem.accountName, icon: TrendingUp },
                                { label: "최초 등록일", value: formatDate(selectedItem.linkedAt), icon: Calendar }
                            ].map((info, i) => (
                                <div key={i} className="p-4 rounded-2xl bg-muted/30 border border-border/50 hover:bg-muted/50 transition-colors">
                                    <p className="text-[10px] font-black text-muted-foreground uppercase tracking-widest mb-1">{info.label}</p>
                                    <p className="font-bold text-sm truncate">{info.value || "-"}</p>
                                </div>
                            ))}
                        </div>

                        {/* Pricing section */}
                        <div className="p-6 rounded-2xl bg-primary shadow-2xl shadow-primary/20 text-white relative overflow-hidden group">
                            <div className="absolute -right-4 -bottom-4 opacity-10 group-hover:scale-125 transition-transform duration-700">
                                <ArrowUpRight className="h-32 w-32" />
                            </div>
                            <p className="text-[10px] font-black uppercase tracking-[0.2em] mb-2 opacity-80">Market Listing Price</p>
                            <div className="flex items-baseline gap-2">
                                <span className="text-4xl font-black font-mono">{selectedItem.sellingPrice.toLocaleString()}</span>
                                <span className="text-lg font-bold opacity-80">KRW</span>
                            </div>
                        </div>

                        {/* Status Note */}
                        <div className="p-5 rounded-2xl bg-blue-500/5 border border-blue-500/10 space-y-3">
                            <div className="flex items-center gap-2 text-blue-600">
                                <AlertCircle className="h-4 w-4" />
                                <span className="text-sm font-black italic">Market Insight</span>
                            </div>
                            <p className="text-[13px] text-blue-700/80 font-medium leading-relaxed">
                                본 상품은 현재 {selectedItem.marketCode} 마켓에 정상 등록되어 판매 중입니다.
                                '프리미엄 고도화' 기능을 통해 AI가 상품명, 속성, 상세페이지를 분석하여 검색 최적화를 진행할 수 있습니다.
                            </p>
                        </div>
                    </div>
                )}
            </Drawer>
        </div>
    );
}
