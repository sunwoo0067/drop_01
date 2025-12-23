"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { MarketProduct } from "@/types";
import { Loader2, RefreshCw, RefreshCcw, AlertTriangle, Trash2, Ban } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";

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

export default function ProductListPage() {
    const router = useRouter();
    const [products, setProducts] = useState<MarketProduct[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedIds, setSelectedIds] = useState<string[]>([]);
    const [isRegistering, setIsRegistering] = useState(false);
    const [bulkAction, setBulkAction] = useState<"update" | "stop" | "delete" | null>(null);

    const fetchProducts = async () => {
        setLoading(true);
        try {
            const response = await api.get("/market/products", { params: { limit: 200 } });
            const items = Array.isArray(response.data?.items) ? response.data.items : [];
            if (items.length > 0) {
                setProducts(items);
            } else {
                const rawRes = await api.get("/market/products/raw", { params: { limit: 200 } });
                setProducts(Array.isArray(rawRes.data?.items) ? rawRes.data.items : []);
            }
            setSelectedIds([]); // Reset selection on refresh
        } catch (error) {
            console.error("Failed to fetch products", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchProducts();
    }, []);

    const handleBulkRegister = async () => {
        if (selectedIds.length === 0) {
            if (!confirm("선택된 상품이 없습니다. '처리완료(COMPLETED)' 상태인 모든 상품을 등록하시겠습니까?")) return;
        } else {
            if (!confirm(`선택된 ${selectedIds.length}개 상품을 쿠팡에 등록하시겠습니까?`)) return;
        }

        setIsRegistering(true);
        try {
            const selectedProducts = getSelectedProducts();
            const productIds = selectedProducts
                .map((product) => product.productId)
                .filter((id): id is string => Boolean(id));
            if (selectedIds.length > 0 && productIds.length === 0) {
                alert("선택된 항목 중 내부 상품과 연결된 항목이 없습니다.");
                return;
            }
            await api.post("/coupang/register/bulk", {
                productIds: selectedIds.length > 0 ? productIds : null
            });
            alert("대량 등록 작업이 시작되었습니다. 결과는 잠시 후 확인해주세요.");
            setSelectedIds([]);
            fetchProducts();
        } catch (error) {
            console.error("Bulk registration failed", error);
            alert("대량 등록 요청 실패");
        } finally {
            setIsRegistering(false);
        }
    };

    const handleSyncStatus = async (productId: string) => {
        try {
            await api.post(`/coupang/sync-status/${productId}`);
            alert("상태 동기화 완료");
            fetchProducts();
        } catch (error) {
            console.error("Sync failed", error);
            alert("상태 동기화 실패");
        }
    };

    const handleStopSales = async (sellerProductId: string) => {
        if (!confirm("쿠팡 판매를 중지하시겠습니까?")) return;
        try {
            await api.post(`/coupang/products/${sellerProductId}/stop-sales`);
            alert("판매중지 요청 완료");
            fetchProducts();
        } catch (error) {
            console.error("Stop sales failed", error);
            alert("판매중지 실패");
        }
    };

    const handleUpdateCoupang = async (productId: string) => {
        if (!confirm("쿠팡 상품 정보를 업데이트하시겠습니까?")) return;
        try {
            await api.put(`/coupang/products/${productId}`);
            alert("쿠팡 수정 요청 완료");
            fetchProducts();
        } catch (error) {
            console.error("Update failed", error);
            alert("수정 실패");
        }
    };

    const getSelectedProducts = () => products.filter((product) => selectedIds.includes(product.marketItemId));

    const handleBulkUpdate = async () => {
        if (selectedIds.length === 0) {
            alert("먼저 변경할 상품을 선택해주세요.");
            return;
        }
        if (!confirm(`선택된 ${selectedIds.length}개 상품을 쿠팡에 수정 반영하시겠습니까?`)) return;

        const updateTargets = getSelectedProducts().filter((product) => product.productId);
        if (updateTargets.length === 0) {
            alert("내부 상품과 연결된 항목이 없습니다. (수정은 연결된 상품만 가능)");
            return;
        }

        setBulkAction("update");
        try {
            const results = await Promise.allSettled(
                updateTargets.map((product) => api.put(`/coupang/products/${product.productId}`))
            );
            const failed = results.filter((r) => r.status === "rejected").length;
            alert(`쿠팡 일괄 수정 완료 (실패 ${failed}건)`);
            fetchProducts();
        } catch (error) {
            console.error("Bulk update failed", error);
            alert("일괄 수정 실패");
        } finally {
            setBulkAction(null);
        }
    };

    const handleBulkStopSales = async () => {
        if (selectedIds.length === 0) {
            alert("먼저 변경할 상품을 선택해주세요.");
            return;
        }
        if (!confirm(`선택된 ${selectedIds.length}개 상품의 판매를 중지하시겠습니까?`)) return;

        setBulkAction("stop");
        try {
            const results = await Promise.allSettled(
                getSelectedProducts().map((product) => api.post(`/coupang/products/${product.marketItemId}/stop-sales`))
            );
            const failed = results.filter((r) => r.status === "rejected").length;
            alert(`판매중지 완료 (실패 ${failed}건)`);
            fetchProducts();
        } catch (error) {
            console.error("Bulk stop sales failed", error);
            alert("판매중지 실패");
        } finally {
            setBulkAction(null);
        }
    };

    const handleBulkDelete = async () => {
        if (selectedIds.length === 0) {
            alert("먼저 변경할 상품을 선택해주세요.");
            return;
        }
        if (!confirm(`선택된 ${selectedIds.length}개 상품을 쿠팡에서 삭제하시겠습니까?`)) return;

        setBulkAction("delete");
        try {
            const results = await Promise.allSettled(
                getSelectedProducts().map((product) => api.delete(`/coupang/products/${product.marketItemId}`))
            );
            const failed = results.filter((r) => r.status === "rejected").length;
            alert(`삭제 완료 (실패 ${failed}건)`);
            fetchProducts();
        } catch (error) {
            console.error("Bulk delete failed", error);
            alert("삭제 실패");
        } finally {
            setBulkAction(null);
        }
    };

    const handleDeleteCoupang = async (sellerProductId: string) => {
        if (!confirm("쿠팡 상품을 삭제하시겠습니까? (판매중지 후 삭제 시도)")) return;
        try {
            await api.delete(`/coupang/products/${sellerProductId}`);
            alert("삭제 요청 완료");
            fetchProducts();
        } catch (error) {
            console.error("Delete failed", error);
            alert("삭제 실패");
        }
    };

    const toggleSelectAll = (checked: boolean) => {
        if (checked) {
            setSelectedIds(products.map(p => p.marketItemId));
        } else {
            setSelectedIds([]);
        }
    };

    const toggleSelect = (id: string, checked: boolean) => {
        if (checked) {
            setSelectedIds(prev => [...prev, id]);
        } else {
            setSelectedIds(prev => prev.filter(item => item !== id));
        }
    };

    const getStatusBadge = (product: MarketProduct) => {
        const listingStatus = String(product.status || "").toUpperCase();
        if (["ON_SALE", "ONSALE", "SALE", "SELLING"].includes(listingStatus)) {
            return <Badge variant="success">판매중</Badge>;
        }
        if (["SUSPENDED", "STOPPED", "OUT_OF_STOCK"].includes(listingStatus)) {
            return <Badge variant="warning">판매중지</Badge>;
        }
        if (listingStatus === "ACTIVE") return <Badge variant="success">판매중</Badge>;
        if (listingStatus === "SUSPENDED") return <Badge variant="warning">판매중지</Badge>;
        return <Badge variant="secondary">{product.status}</Badge>;
    };

    const getCoupangStatusBadge = (product: MarketProduct) => {
        const cpStatus = normalizeCoupangStatus(product.coupangStatus);
        if (!cpStatus) return null;

        if (cpStatus === 'DENIED') return <Badge variant="destructive">반려</Badge>;
        if (cpStatus === 'DELETED') return <Badge variant="destructive">삭제</Badge>;
        if (cpStatus === 'IN_REVIEW') return <Badge variant="secondary" className="bg-blue-100 text-blue-700 border-none">심사중</Badge>;
        if (cpStatus === 'APPROVING') return <Badge variant="secondary" className="bg-blue-100 text-blue-700 border-none">승인대기</Badge>;
        if (cpStatus === 'SAVED') return <Badge variant="secondary">임시저장</Badge>;
        if (cpStatus === 'PARTIAL_APPROVED') return <Badge variant="success">부분승인</Badge>;
        if (cpStatus === 'APPROVED') return <Badge variant="success">승인</Badge>;
        return <Badge variant="secondary">{cpStatus}</Badge>;
    };

    const getActiveListing = (product: MarketProduct) => product.marketItemId ? product : undefined;

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <h1 className="text-3xl font-bold tracking-tight">상품 목록</h1>
                <div className="flex gap-2">
                    <Button onClick={handleBulkRegister} disabled={loading || isRegistering} variant="primary">
                        {isRegistering ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                        쿠팡 일괄 등록
                    </Button>
                    <Button
                        onClick={async () => {
                            setLoading(true);
                            try {
                                const resp = await api.post("/market/products/sync", null, { params: { deep: true } });
                                const message = resp.data?.message || "쿠팡 상품 동기화가 시작되었습니다. 잠시 후 새로고침하여 확인해주세요.";
                                alert(message);
                                await fetchProducts();
                            } catch (error) {
                                console.error("Sync products failed", error);
                                alert("쿠팡 상품 동기화 실패");
                            } finally {
                                setLoading(false);
                            }
                        }}
                        disabled={loading}
                        variant="outline"
                    >
                        <RefreshCcw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                        쿠팡 동기화
                    </Button>
                    <Button onClick={handleBulkUpdate} disabled={loading || bulkAction !== null} variant="outline">
                        {bulkAction === "update" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                        일괄 수정
                    </Button>
                    <Button onClick={handleBulkStopSales} disabled={loading || bulkAction !== null} variant="outline">
                        {bulkAction === "stop" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Ban className="mr-2 h-4 w-4" />}
                        판매중지
                    </Button>
                    <Button onClick={handleBulkDelete} disabled={loading || bulkAction !== null} variant="outline">
                        {bulkAction === "delete" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
                        삭제
                    </Button>
                    <Button onClick={fetchProducts} disabled={loading} variant="outline">
                        <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                        새로고침
                    </Button>
                </div>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>등록 상품 관리</CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <table className="w-full caption-bottom text-sm text-left">
                            <thead className="[&_tr]:border-b">
                                <tr className="border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted">
                                    <th className="h-12 px-4 align-middle font-medium text-muted-foreground w-[40px]">
                                        <input
                                            type="checkbox"
                                            className="h-4 w-4 rounded border-gray-300"
                                            checked={products.length > 0 && selectedIds.length === products.length}
                                            onChange={(e) => toggleSelectAll(e.target.checked)}
                                        />
                                    </th>
                                    <th className="h-12 px-4 align-middle font-medium text-muted-foreground w-[100px]">이미지</th>
                                    <th className="h-12 px-4 align-middle font-medium text-muted-foreground">상품명</th>
                                    <th className="h-12 px-4 align-middle font-medium text-muted-foreground">가격</th>
                                    <th className="h-12 px-4 align-middle font-medium text-muted-foreground">상태</th>
                                    <th className="h-12 px-4 align-middle font-medium text-muted-foreground text-right">작업</th>
                                </tr>
                            </thead>
                            <tbody className="[&_tr:last-child]:border-0">
                                {loading ? (
                                    <tr>
                                        <td colSpan={6} className="h-24 text-center">
                                            <Loader2 className="mx-auto h-6 w-6 animate-spin text-muted-foreground" />
                                        </td>
                                    </tr>
                                ) : products.length === 0 ? (
                                    <tr>
                                        <td colSpan={6} className="h-24 text-center text-muted-foreground">
                                            등록된 상품이 없습니다.
                                        </td>
                                    </tr>
                                ) : (
                                    products.map((product) => (
                                        <tr key={product.id} className="border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted">
                                            <td className="p-4 align-middle">
                                                <input
                                                    type="checkbox"
                                                    className="h-4 w-4 rounded border-gray-300"
                                                    checked={selectedIds.includes(product.marketItemId)}
                                                    onChange={(e) => toggleSelect(product.marketItemId, e.target.checked)}
                                                />
                                            </td>
                                            <td className="p-4 align-middle">
                                                {product.processedImageUrls && product.processedImageUrls.length > 0 ? (
                                                    <img src={product.processedImageUrls[0]} alt={product.name || ""} className="h-12 w-12 object-cover rounded-md border" />
                                                ) : (
                                                    <div className="h-12 w-12 bg-muted rounded-md border flex items-center justify-center text-xs text-muted-foreground">No img</div>
                                                )}
                                            </td>
                                            <td className="p-4 align-middle">
                                                <div className="font-medium line-clamp-1">{product.processedName || product.name}</div>
                                                <div className="text-xs text-muted-foreground">{product.marketItemId}</div>
                                            </td>
                                            <td className="p-4 align-middle">
                                                {product.sellingPrice?.toLocaleString()} 원
                                            </td>
                                            <td className="p-4 align-middle">
                                                <div className="flex flex-col gap-1">
                                                    {getStatusBadge(product)}
                                                    {getCoupangStatusBadge(product)}
                                                    {getActiveListing(product) && (
                                                        <span className="text-[10px] text-muted-foreground">Coupang Linked</span>
                                                    )}
                                                </div>
                                            </td>
                                            <td className="p-4 align-middle text-right">
                                                <div className="flex justify-end gap-2">
                                                    {getActiveListing(product) && (
                                                        <>
                                                            {product.productId && (
                                                                <>
                                                                    <Button size="icon" variant="ghost" onClick={() => handleSyncStatus(product.productId!)} title="상태 동기화">
                                                                        <RefreshCcw className="h-4 w-4" />
                                                                    </Button>
                                                                    <Button size="icon" variant="ghost" onClick={() => handleUpdateCoupang(product.productId!)} title="쿠팡 수정">
                                                                        <RefreshCw className="h-4 w-4" />
                                                                    </Button>
                                                                </>
                                                            )}
                                                            <Button
                                                                size="icon"
                                                                variant="ghost"
                                                                onClick={() => handleStopSales(product.marketItemId)}
                                                                title="판매중지"
                                                            >
                                                                <AlertTriangle className="h-4 w-4" />
                                                            </Button>
                                                            <Button
                                                                size="icon"
                                                                variant="ghost"
                                                                onClick={() => handleDeleteCoupang(product.marketItemId)}
                                                                title="삭제"
                                                            >
                                                                <Trash2 className="h-4 w-4" />
                                                            </Button>
                                                        </>
                                                    )}
                                                    {product.productId && (
                                                        <Button size="sm" variant="outline" onClick={() => router.push(`/products/${product.productId}`)}>
                                                            수정
                                                        </Button>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
