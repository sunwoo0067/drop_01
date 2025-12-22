"use client";

import { useEffect, useState } from "react";
import {
    Loader2,
    Search,
    Upload,
    CheckCircle2,
    Clock,
    AlertCircle,
    RotateCw,
    Sparkles,
    ShoppingCart,
    ArrowRight,
    RefreshCcw,
    AlertTriangle
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import api from "@/lib/api";
import { Product } from "@/types";
import { cn } from "@/lib/utils";

interface RegistrationProduct extends Product {
    imagesCount: number;
    coupangStatus?: string | null;
    rejectionReason?: any;
    forbiddenTags?: string[];
}

function normalizeCoupangStatus(status?: string | null): string | null {
    if (!status) return null;
    const s = String(status).trim();
    if (!s) return null;

    const su = s.toUpperCase();
    if (su === "APPROVAL_REQUESTED") {
        return "APPROVING";
    }
    if (
        su === "DENIED" ||
        su === "DELETED" ||
        su === "IN_REVIEW" ||
        su === "SAVED" ||
        su === "APPROVING" ||
        su === "APPROVED" ||
        su === "PARTIAL_APPROVED"
    ) {
        return su;
    }

    if (s === "승인반려" || s === "반려") return "DENIED";
    if (s === "심사중") return "IN_REVIEW";
    if (s === "승인대기중") return "APPROVING";
    if (s === "승인완료") return "APPROVED";
    if (s === "부분승인완료") return "PARTIAL_APPROVED";
    if (s === "임시저장" || s === "임시저장중") return "SAVED";
    if (s.includes("삭제") || s === "상품삭제") return "DELETED";

    return s;
}

export default function RegistrationPage() {
    const [items, setItems] = useState<RegistrationProduct[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState("");
    const [registeringIds, setRegisteringIds] = useState<Set<string>>(new Set());
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
    const [bulkRegistering, setBulkRegistering] = useState(false);

    // 가공 완료 + DRAFT 상태 상품 조회
    const fetchProducts = async () => {
        setLoading(true);
        setError(null);
        try {
            // DRAFT 상품 중 COMPLETED 가공 상태인 것 + MarketListing의 coupang_status가 DENIED인 것 조회
            const response = await api.get("/products/", {
                params: {
                    processingStatus: "COMPLETED",
                    // status 필터는 백엔드에서 DRAFT만 가져오도록 되어있을 수 있으므로 
                    // 모든 DRAFT 상품을 가져온 후 프론트엔드에서 추가 필터링
                    status: "DRAFT"
                }
            });
            const products = Array.isArray(response.data) ? response.data : [];

            const processed = products.map((p: Product) => {
                const coupangListing = p.market_listings?.find(l => l.market_item_id);
                return {
                    ...p,
                    imagesCount: p.processed_image_urls?.length || 0,
                    coupangStatus: coupangListing?.coupang_status,
                    rejectionReason: coupangListing?.rejection_reason,
                    forbiddenTags: []
                };
            });
            const ids = processed.map((p) => p.id);
            if (ids.length > 0) {
                try {
                    const warningsRes = await api.post("/products/html-warnings", {
                        productIds: ids,
                    });
                    const warningsList = Array.isArray(warningsRes.data) ? warningsRes.data : [];
                    const warningsMap = new Map<string, string[]>();
                    warningsList.forEach((w: any) => {
                        if (w?.productId) warningsMap.set(w.productId, w.tags || []);
                    });
                    const withWarnings = processed.map((item) => ({
                        ...item,
                        forbiddenTags: warningsMap.get(item.id) || [],
                    }));
                    setItems(withWarnings);
                } catch (warnErr) {
                    console.error("Failed to fetch HTML warnings", warnErr);
                    setItems(processed);
                }
            } else {
                setItems(processed);
            }
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

    // 개별 상품 쿠팡 등록
    const handleRegister = async (productId: string) => {
        if (registeringIds.has(productId)) return;

        setRegisteringIds(prev => new Set(prev).add(productId));
        try {
            await api.post(`/coupang/register/${productId}`, null, {
                params: { autoFix: true, wait: true }
            });
            // 등록 성공 시 목록에서 제거
            setItems(prev => prev.filter(item => item.id !== productId));
            setSelectedIds(prev => {
                const next = new Set(prev);
                next.delete(productId);
                return next;
            });
        } catch (e: any) {
            console.error("Registration failed", e);
            const detail = e.response?.data?.detail;
            const message = typeof detail === 'string' ? detail : detail?.message || "등록 실패";
            alert(`등록 실패: ${message}`);
        } finally {
            setRegisteringIds(prev => {
                const next = new Set(prev);
                next.delete(productId);
                return next;
            });
        }
    };

    // 일괄 등록
    const handleBulkRegister = async () => {
        if (selectedIds.size === 0) {
            alert("등록할 상품을 선택해주세요.");
            return;
        }

        setBulkRegistering(true);
        try {
            const productIds = Array.from(selectedIds);
            await api.post("/coupang/register/bulk",
                { productIds },
                { params: { autoFix: true, wait: true, limit: 50 } }
            );
            // 등록 완료된 상품들 목록에서 제거
            setItems(prev => prev.filter(item => !selectedIds.has(item.id)));
            setSelectedIds(new Set());
            alert("일괄 등록이 완료되었습니다.");
        } catch (e: any) {
            console.error("Bulk registration failed", e);
            alert("일괄 등록 중 오류가 발생했습니다.");
        } finally {
            setBulkRegistering(false);
        }
    };

    const handleSyncStatus = async (productId: string) => {
        try {
            const resp = await api.post(`/coupang/sync-status/${productId}`);
            const newStatus = normalizeCoupangStatus(resp.data.coupangStatus);

            // 상태 업데이트 후, 만약 DENIED가 아니게 되었다면 목록 유지 또는 변경
            // 여기서는 단순히 상태값만 업데이트해서 리렌더링 유도
            setItems(prev => prev.map(item => {
                if (item.id === productId) {
                    return { ...item, coupangStatus: newStatus };
                }
                return item;
            }));

            if (newStatus === 'APPROVED') {
                alert("상품이 승인되었습니다! 목록에서 제거합니다.");
                setItems(prev => prev.filter(item => item.id !== productId));
            } else {
                alert(`동기화 완료: ${newStatus}`);
            }
        } catch (e: any) {
            console.error("Sync failed", e);
            alert("상태 동기화에 실패했습니다.");
        }
    };

    const handleResetPending = async () => {
        if (!confirm("등록 대기 상품을 모두 삭제하시겠습니까?")) return;
        try {
            await api.post("/products/registration/pending/clear");
            setSearchTerm("");
            setSelectedIds(new Set());
            await fetchProducts();
            alert("등록 대기 상품이 삭제되었습니다.");
        } catch (e) {
            console.error("Failed to clear pending products", e);
            alert("등록 대기 초기화에 실패했습니다.");
        }
    };

    // 전체 선택/해제
    const toggleSelectAll = (checked: boolean) => {
        if (checked) {
            const readyIds = filteredItems
                .filter(item => item.imagesCount >= 1)
                .map(item => item.id);
            setSelectedIds(new Set(readyIds));
        } else {
            setSelectedIds(new Set());
        }
    };

    // 개별 선택/해제
    const toggleSelect = (id: string, checked: boolean) => {
        setSelectedIds(prev => {
            const next = new Set(prev);
            if (checked) {
                next.add(id);
            } else {
                next.delete(id);
            }
            return next;
        });
    };

    // 등록 가능 여부 체크 (이미지 1장 이상)
    const isReadyForRegistration = (item: RegistrationProduct) => {
        return item.imagesCount >= 1;
    };

    const filteredItems = items.filter(item =>
        item.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.processed_name?.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const readyCount = filteredItems.filter(isReadyForRegistration).length;
    const notReadyCount = filteredItems.length - readyCount;

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
            {/* Header Section */}
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 pb-6 border-b">
                <div className="space-y-2">
                    <div className="flex items-center gap-2 text-primary font-medium">
                        <Upload className="h-5 w-5" />
                        <span>Market Registration</span>
                    </div>
                    <h1 className="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
                        상품 등록
                    </h1>
                    <p className="text-muted-foreground max-w-2xl">
                        가공 완료된 상품을 쿠팡 마켓에 등록합니다. 이미지가 1장 이상인 상품만 등록 가능합니다.
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <Button variant="outline" className="rounded-xl h-11 px-6 border-2 hover:bg-accent" onClick={fetchProducts}>
                        <RotateCw className="mr-2 h-4 w-4" />
                        새로고침
                    </Button>
                    <Button variant="outline" className="rounded-xl h-11 px-6 border-2 hover:bg-accent" onClick={handleResetPending}>
                        <RefreshCcw className="mr-2 h-4 w-4" />
                        등록대기 초기화
                    </Button>
                    <Button
                        className="rounded-xl h-11 px-6 shadow-lg shadow-primary/20 hover:scale-105 transition-transform"
                        onClick={handleBulkRegister}
                        disabled={selectedIds.size === 0 || bulkRegistering}
                    >
                        {bulkRegistering ? (
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : (
                            <Sparkles className="mr-2 h-4 w-4" />
                        )}
                        선택 등록 ({selectedIds.size})
                    </Button>
                </div>
            </div>

            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card className="border-none shadow-md bg-gradient-to-br from-blue-500/10 to-blue-600/5">
                    <CardContent className="p-6">
                        <div className="flex items-center gap-4">
                            <div className="h-12 w-12 rounded-xl bg-blue-500/20 flex items-center justify-center">
                                <Clock className="h-6 w-6 text-blue-500" />
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">등록 대기</p>
                                <p className="text-3xl font-bold">{filteredItems.length}</p>
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
                                <p className="text-sm text-muted-foreground">등록 가능</p>
                                <p className="text-3xl font-bold">{readyCount}</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
                <Card className="border-none shadow-md bg-gradient-to-br from-amber-500/10 to-amber-600/5">
                    <CardContent className="p-6">
                        <div className="flex items-center gap-4">
                            <div className="h-12 w-12 rounded-xl bg-amber-500/20 flex items-center justify-center">
                                <AlertCircle className="h-6 w-6 text-amber-500" />
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">이미지 부족</p>
                                <p className="text-3xl font-bold">{notReadyCount}</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Search and Filters */}
            <div className="flex flex-col md:flex-row gap-4 items-center">
                <div className="relative flex-1 group w-full">
                    <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground group-focus-within:text-primary transition-colors" />
                    <Input
                        placeholder="상품명으로 검색..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="pl-12 h-12 rounded-2xl border-none bg-accent/50 focus-visible:ring-2 focus-visible:ring-primary/20 transition-all text-base w-full"
                    />
                </div>
                <div className="flex items-center gap-2">
                    <input
                        type="checkbox"
                        id="selectAll"
                        checked={selectedIds.size === readyCount && readyCount > 0}
                        onChange={(e) => toggleSelectAll(e.target.checked)}
                        className="h-5 w-5 rounded border-gray-300"
                    />
                    <label htmlFor="selectAll" className="text-sm text-muted-foreground">
                        등록 가능 전체 선택
                    </label>
                </div>
                <Button
                    variant="outline"
                    className="h-12 rounded-2xl px-6"
                    onClick={() => window.location.href = '/market-products'}
                >
                    마켓 상품 보기
                    <ArrowRight className="ml-2 h-4 w-4" />
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
                            <CheckCircle2 className="h-10 w-10 text-muted-foreground/50" />
                        </div>
                        <h3 className="text-2xl font-bold text-foreground mb-2">등록 대기 상품이 없습니다</h3>
                        <p className="text-muted-foreground">가공 페이지에서 상품을 가공해 주세요.</p>
                        <Button className="mt-8 rounded-xl h-11 px-8" onClick={() => window.location.href = '/processing'}>가공 페이지로 이동</Button>
                    </div>
                ) : (
                    filteredItems.map((item) => {
                        const isReady = isReadyForRegistration(item);
                        const isRegistering = registeringIds.has(item.id);
                        const isSelected = selectedIds.has(item.id);

                        return (
                            <Card
                                key={item.id}
                                className={cn(
                                    "group overflow-hidden border-2 shadow-md hover:shadow-2xl transition-all duration-500 rounded-3xl bg-card/40 backdrop-blur-xl",
                                    isSelected ? "border-primary" : "border-transparent",
                                    !isReady && "opacity-70"
                                )}
                            >
                                {/* Image Preview */}
                                <div className="aspect-[4/3] relative overflow-hidden bg-muted">
                                    {item.processed_image_urls && item.processed_image_urls.length > 0 ? (
                                        <img
                                            src={item.processed_image_urls[0]}
                                            alt={item.name}
                                            className="object-cover w-full h-full transition-transform duration-700 group-hover:scale-110"
                                        />
                                    ) : (
                                        <div className="w-full h-full flex flex-col items-center justify-center text-muted-foreground/30 space-y-2">
                                            <ShoppingCart className="h-12 w-12" />
                                            <span className="text-xs font-medium uppercase tracking-widest">No Image</span>
                                        </div>
                                    )}

                                    {/* Select Checkbox */}
                                    {isReady && (
                                        <div className="absolute top-4 left-4">
                                            <input
                                                type="checkbox"
                                                checked={isSelected}
                                                onChange={(e) => toggleSelect(item.id, e.target.checked)}
                                                className="h-5 w-5 rounded border-2 border-white bg-white/80 backdrop-blur-sm"
                                            />
                                        </div>
                                    )}

                                    {/* Image Count Badge */}
                                    <div className="absolute top-4 right-4">
                                        <Badge
                                            className={cn(
                                                "backdrop-blur-md border-0 text-[10px] font-bold tracking-widest uppercase py-1",
                                                isReady ? "bg-emerald-500/80 text-white" : "bg-amber-500/80 text-white"
                                            )}
                                        >
                                            이미지 {item.imagesCount}/1
                                        </Badge>
                                    </div>
                                </div>

                                <CardContent className="p-5 space-y-4">
                                    <div className="space-y-1">
                                        <div className="flex items-center gap-2">
                                            <h3 className="font-bold text-lg leading-tight truncate group-hover:text-primary transition-colors">
                                                {item.processed_name || item.name}
                                            </h3>
                                            {item.forbiddenTags && item.forbiddenTags.length > 0 && (
                                                <Badge variant="warning" className="text-[10px]">
                                                    금지 태그
                                                </Badge>
                                            )}
                                        </div>
                                        {item.processed_name && (
                                            <p className="text-xs text-muted-foreground line-through opacity-50 truncate">
                                                {item.name}
                                            </p>
                                        )}
                                        {item.forbiddenTags && item.forbiddenTags.length > 0 && (
                                            <p className="text-[10px] text-amber-600">
                                                {item.forbiddenTags.join(", ")}
                                            </p>
                                        )}
                                    </div>

                                    <div className="flex items-center justify-between text-sm py-3 border-y border-foreground/5">
                                        <div className="flex flex-col">
                                            <span className="text-muted-foreground text-[10px] uppercase font-bold tracking-tighter">판매가</span>
                                            <span className="font-bold text-base text-primary">{item.selling_price.toLocaleString()}원</span>
                                        </div>
                                        <div className="flex flex-col items-end">
                                            <span className="text-muted-foreground text-[10px] uppercase font-bold tracking-tighter">마켓 상태</span>
                                            {normalizeCoupangStatus(item.coupangStatus) === 'DENIED' ? (
                                                <Badge variant="destructive" className="text-[10px] animate-pulse">
                                                    승인 반려
                                                </Badge>
                                            ) : normalizeCoupangStatus(item.coupangStatus) === 'IN_REVIEW' ? (
                                                <Badge variant="secondary" className="text-[10px] bg-blue-100 text-blue-700">
                                                    심사 중
                                                </Badge>
                                            ) : normalizeCoupangStatus(item.coupangStatus) === 'APPROVING' ? (
                                                <Badge variant="secondary" className="text-[10px] bg-blue-100 text-blue-700">
                                                    승인 대기
                                                </Badge>
                                            ) : normalizeCoupangStatus(item.coupangStatus) === 'SAVED' ? (
                                                <Badge variant="secondary" className="text-[10px]">
                                                    임시 저장
                                                </Badge>
                                            ) : normalizeCoupangStatus(item.coupangStatus) === 'APPROVED' ? (
                                                <Badge variant="success" className="text-[10px]">
                                                    승인 완료
                                                </Badge>
                                            ) : (
                                                <Badge variant="secondary" className="text-[10px]">
                                                    {isReady ? "등록 가능" : "이미지 부족"}
                                                </Badge>
                                            )}
                                        </div>
                                    </div>

                                    {normalizeCoupangStatus(item.coupangStatus) === 'DENIED' && item.rejectionReason && (
                                        <div className="p-3 rounded-xl bg-destructive/5 border border-destructive/10 space-y-2">
                                            <div className="flex items-center gap-2 text-destructive">
                                                <AlertTriangle className="h-4 w-4" />
                                                <span className="text-xs font-bold">반려 사유</span>
                                            </div>
                                            <p className="text-xs text-destructive/80 leading-relaxed line-clamp-3">
                                                {item.rejectionReason.reason || "상세 사유 없음"}
                                            </p>
                                        </div>
                                    )}
                                </CardContent>

                                <CardFooter className="px-5 pb-5 pt-0">
                                    <div className="flex flex-col gap-2 w-full">
                                        <Button
                                            className={cn(
                                                "w-full rounded-2xl font-bold transition-all shadow-lg",
                                                isReady
                                                    ? "bg-primary hover:bg-primary/90 shadow-primary/20"
                                                    : "bg-muted text-muted-foreground cursor-not-allowed"
                                            )}
                                            size="sm"
                                            onClick={() => handleRegister(item.id)}
                                            disabled={!isReady || isRegistering}
                                        >
                                            {isRegistering ? (
                                                <>
                                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                                    처리 중...
                                                </>
                                            ) : normalizeCoupangStatus(item.coupangStatus) === 'DENIED' ? (
                                                <>
                                                    <RotateCw className="mr-2 h-4 w-4" />
                                                    수정 및 재등록
                                                </>
                                            ) : isReady ? (
                                                <>
                                                    <Upload className="mr-2 h-4 w-4" />
                                                    쿠팡 등록
                                                </>
                                            ) : (
                                                "이미지 추가 필요"
                                            )}
                                        </Button>

                                        {item.coupangStatus && (
                                            <Button
                                                variant="outline"
                                                className="w-full rounded-2xl text-xs h-8 border-dashed"
                                                onClick={() => handleSyncStatus(item.id)}
                                            >
                                                <RefreshCcw className="mr-2 h-3 w-3" />
                                                상태 동기화
                                            </Button>
                                        )}
                                    </div>
                                </CardFooter>
                            </Card>
                        );
                    })
                )}
            </div>
        </div>
    );
}
