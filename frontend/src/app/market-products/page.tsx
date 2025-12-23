"use client";

import { useEffect, useState } from "react";
import {
    Loader2,
    Search,
    ShoppingBag,
    ExternalLink,
    RotateCw,
    AlertCircle,
    CheckCircle2,
    Edit,
    Trash2,
    MoreVertical,
    ArrowLeft
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import api from "@/lib/api";
import { cn } from "@/lib/utils";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue
} from "@/components/ui/Select";

interface MarketAccount {
    id: string;
    name: string;
    marketCode: string;
}

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
    marketAccountId: string;
    accountName: string | null;
    marketCode: string;
}

export default function MarketProductsPage() {
    const [items, setItems] = useState<MarketProduct[]>([]);
    const [loading, setLoading] = useState(true);
    const [accounts, setAccounts] = useState<MarketAccount[]>([]);
    const [selectedAccountId, setSelectedAccountId] = useState<string>("all");
    const [error, setError] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState("");
    const [total, setTotal] = useState(0);

    const fetchAccounts = async () => {
        try {
            const [coupangRes, smartstoreRes] = await Promise.all([
                api.get("/settings/markets/coupang/accounts"),
                api.get("/settings/markets/smartstore/accounts")
            ]);

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

            setAccounts([...coupangAccounts, ...smartstoreAccounts]);
        } catch (e) {
            console.error("Failed to fetch accounts", e);
        }
    };

    const fetchMarketProducts = async (accountId?: string) => {
        setLoading(true);
        setError(null);
        try {
            const params: any = { limit: 100 };
            const effectiveAccountId = accountId !== undefined ? accountId : selectedAccountId;
            if (effectiveAccountId && effectiveAccountId !== "all") {
                params.accountId = effectiveAccountId;
            }

            const response = await api.get("/market/products", { params });
            const data = response.data;
            setItems(Array.isArray(data.items) ? data.items : []);
            setTotal(data.total || 0);
        } catch (e) {
            console.error("Failed to fetch market products", e);
            setError("마켓 상품 목록을 불러오지 못했습니다.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAccounts();
        fetchMarketProducts();
    }, []);

    const handleAccountChange = (value: string) => {
        setSelectedAccountId(value);
        fetchMarketProducts(value);
    };

    // 쿠팡 상품 상세 보기 (새 탭)
    const handleViewOnCoupang = (sellerProductId: string) => {
        // 쿠팡 Wing 판매자 센터 상품 조회 URL (로그인 필요)
        window.open(`https://wing.coupang.com/product/${sellerProductId}`, '_blank');
    };

    const filteredItems = items.filter(item =>
        (item.name || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
        (item.processedName || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.marketItemId.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const formatDate = (dateStr: string | null) => {
        if (!dateStr) return "-";
        const date = new Date(dateStr);
        return date.toLocaleDateString('ko-KR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
            {/* 헤더 섹션 */}
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 pb-6 border-b">
                <div className="space-y-2">
                    <div className="flex items-center gap-2 text-primary font-medium">
                        <ShoppingBag className="h-5 w-5" />
                        <span>Market Products</span>
                    </div>
                    <h1 className="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
                        마켓 상품
                    </h1>
                    <p className="text-muted-foreground max-w-2xl">
                        쿠팡에 등록된 상품 목록입니다. 등록된 상품의 상태를 확인하고 관리할 수 있습니다.
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <Button
                        variant="outline"
                        className="rounded-xl h-11 px-6 border-2 hover:bg-accent"
                        onClick={() => window.location.href = '/registration'}
                    >
                        <ArrowLeft className="mr-2 h-4 w-4" />
                        등록 페이지
                    </Button>
                    <Button variant="outline" className="rounded-xl h-11 px-6 border-2 hover:bg-accent" onClick={fetchMarketProducts}>
                        <RotateCw className="mr-2 h-4 w-4" />
                        새로고침
                    </Button>
                </div>
            </div>

            {/* 통계 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card className="border-none shadow-md bg-gradient-to-br from-primary/10 to-primary/5">
                    <CardContent className="p-6">
                        <div className="flex items-center gap-4">
                            <div className="h-12 w-12 rounded-xl bg-primary/20 flex items-center justify-center">
                                <ShoppingBag className="h-6 w-6 text-primary" />
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">등록된 상품</p>
                                <p className="text-3xl font-bold">{total}</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
                <Card className="border-none shadow-md bg-gradient-to-br from-emerald-500/10 to-emerald-600/5">
                    <CardContent className="p-6">
                        <div className="flex items-center gap-4">
                            <div className="h-12 w-12 rounded-xl bg-emerald-500/20 flex items-center justify-center">
                                <CheckCircle2 className="h-6 w-6 text-emerald-500" />
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">활성 상품</p>
                                <p className="text-3xl font-bold">{items.filter(i => i.status === "ACTIVE").length}</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* 필터 및 검색 */}
            <div className="flex flex-col md:flex-row gap-4 items-center">
                <div className="w-full md:w-64">
                    <Select value={selectedAccountId} onValueChange={handleAccountChange}>
                        <SelectTrigger className="h-12 rounded-2xl bg-accent/50 border-none focus:ring-2 focus:ring-primary/20">
                            <SelectValue placeholder="모든 계정 보기" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">모든 계정 보기</SelectItem>
                            {accounts.map(acc => (
                                <SelectItem key={acc.id} value={acc.id}>
                                    <span className="flex items-center gap-2">
                                        <Badge variant="outline" className="text-[10px] py-0 h-4 uppercase">
                                            {acc.marketCode}
                                        </Badge>
                                        {acc.name}
                                    </span>
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div className="relative flex-1 group w-full">
                    <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground group-focus-within:text-primary transition-colors" />
                    <Input
                        placeholder="상품명 또는 상품 ID로 검색..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="pl-12 h-12 rounded-2xl border-none bg-accent/50 focus-visible:ring-2 focus-visible:ring-primary/20 transition-all text-base w-full"
                    />
                </div>
            </div>

            {/* 상품 목록 */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {loading ? (
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
                            <Button className="mt-6 rounded-xl" variant="outline" onClick={fetchMarketProducts}>다시 시도</Button>
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
                    filteredItems.map((item) => (
                        <Card
                            key={item.id}
                            className="group overflow-hidden border-none shadow-md hover:shadow-2xl transition-all duration-500 rounded-3xl bg-card/40 backdrop-blur-xl border border-white/10"
                        >
                            {/* 이미지 미리보기 */}
                            <div className="aspect-[4/3] relative overflow-hidden bg-muted">
                                {item.processedImageUrls && item.processedImageUrls.length > 0 ? (
                                    <img
                                        src={item.processedImageUrls[0]}
                                        alt={item.name || "상품"}
                                        className="object-cover w-full h-full transition-transform duration-700 group-hover:scale-110"
                                    />
                                ) : (
                                    <div className="w-full h-full flex flex-col items-center justify-center text-muted-foreground/30 space-y-2">
                                        <ShoppingBag className="h-12 w-12" />
                                        <span className="text-xs font-medium uppercase tracking-widest">No Image</span>
                                    </div>
                                )}

                                {/* 상태 배지 */}
                                <div className="absolute top-4 left-4">
                                    <Badge
                                        className={cn(
                                            "backdrop-blur-md border-0 text-[10px] font-bold tracking-widest uppercase py-1",
                                            item.status === "ACTIVE" ? "bg-emerald-500/80 text-white" : "bg-gray-500/80 text-white"
                                        )}
                                    >
                                        {item.status === "ACTIVE" ? "판매중" : item.status}
                                    </Badge>
                                </div>

                                {/* 마켓 계정 배지 */}
                                <div className="absolute top-4 right-4">
                                    <Badge
                                        className={cn(
                                            "backdrop-blur-md border-0 text-[10px] font-bold py-1",
                                            item.marketCode === "COUPANG" ? "bg-orange-500/80 text-white" : "bg-green-600/80 text-white"
                                        )}
                                    >
                                        {item.accountName || (item.marketCode === "COUPANG" ? "쿠팡" : "스토어")}
                                    </Badge>
                                </div>

                                {/* 외부 링크 */}
                                <div className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <Button
                                        size="icon"
                                        variant="secondary"
                                        className="h-9 w-9 rounded-full shadow-lg"
                                        onClick={() => handleViewOnCoupang(item.marketItemId)}
                                    >
                                        <ExternalLink className="h-4 w-4" />
                                    </Button>
                                </div>
                            </div>

                            <CardContent className="p-5 space-y-4">
                                <div className="space-y-1">
                                    <h3 className="font-bold text-lg leading-tight truncate group-hover:text-primary transition-colors">
                                        {item.processedName || item.name || "상품명 없음"}
                                    </h3>
                                    <p className="text-xs text-muted-foreground truncate">
                                        마켓 ID: {item.marketItemId}
                                    </p>
                                </div>

                                <div className="flex items-center justify-between text-sm py-3 border-y border-foreground/5">
                                    <div className="flex flex-col">
                                        <span className="text-muted-foreground text-[10px] uppercase font-bold tracking-tighter">판매가</span>
                                        <span className="font-bold text-base text-primary">{item.sellingPrice.toLocaleString()}원</span>
                                    </div>
                                    <div className="flex flex-col items-end">
                                        <span className="text-muted-foreground text-[10px] uppercase font-bold tracking-tighter">등록일</span>
                                        <span className="text-sm">{formatDate(item.linkedAt)}</span>
                                    </div>
                                </div>
                            </CardContent>

                            <CardFooter className="px-5 pb-5 pt-0 gap-2">
                                <Button
                                    className="flex-1 rounded-2xl font-bold bg-accent hover:bg-accent/80 text-foreground border-none transition-all"
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleViewOnCoupang(item.marketItemId)}
                                >
                                    <ExternalLink className="mr-2 h-4 w-4" />
                                    쿠팡에서 보기
                                </Button>
                            </CardFooter>
                        </Card>
                    ))
                )}
            </div>
        </div>
    );
}
