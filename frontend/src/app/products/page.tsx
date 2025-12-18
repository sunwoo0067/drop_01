"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { Product } from "@/types";
import { Loader2, RefreshCw, RefreshCcw, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";

export default function ProductListPage() {
    const router = useRouter();
    const [products, setProducts] = useState<Product[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedIds, setSelectedIds] = useState<string[]>([]);
    const [isRegistering, setIsRegistering] = useState(false);

    const fetchProducts = async () => {
        setLoading(true);
        try {
            const response = await api.get("/products/");
            setProducts(response.data);
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

    const handleRegister = async (productId: string) => {
        try {
            if (!confirm("이 상품을 쿠팡에 등록하시겠습니까?")) return;
            await api.post(`/coupang/register/${productId}`);
            alert("등록이 시작되었습니다!");
            fetchProducts();
        } catch (error) {
            console.error("Registration failed", error);
            alert("등록 실패");
        }
    };

    const handleBulkRegister = async () => {
        if (selectedIds.length === 0) {
            if (!confirm("선택된 상품이 없습니다. '처리완료(COMPLETED)' 상태인 모든 상품을 등록하시겠습니까?")) return;
        } else {
            if (!confirm(`선택된 ${selectedIds.length}개 상품을 쿠팡에 등록하시겠습니까?`)) return;
        }

        setIsRegistering(true);
        try {
            await api.post("/coupang/register/bulk", {
                productIds: selectedIds.length > 0 ? selectedIds : null
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

    const toggleSelectAll = (checked: boolean) => {
        if (checked) {
            setSelectedIds(products.map(p => p.id));
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

    const getStatusBadge = (product: Product) => {
        const coupangListing = product.market_listings?.find(l => l.market_item_id);
        const cpStatus = coupangListing?.coupang_status;

        if (cpStatus === 'DENIED') return <Badge variant="destructive">반려</Badge>;
        if (cpStatus === 'IN_REVIEW') return <Badge variant="secondary" className="bg-blue-100 text-blue-700 border-none">심사중</Badge>;
        if (cpStatus === 'APPROVED') return <Badge variant="success">승인</Badge>;

        switch (product.processing_status) {
            case 'COMPLETED': return <Badge variant="success">완료</Badge>;
            case 'FAILED': return <Badge variant="destructive">실패</Badge>;
            case 'PROCESSING': return <Badge variant="warning">처리중</Badge>;
            default: return <Badge variant="secondary">{product.processing_status}</Badge>;
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <h1 className="text-3xl font-bold tracking-tight">상품 목록</h1>
                <div className="flex gap-2">
                    <Button onClick={handleBulkRegister} disabled={loading || isRegistering} variant="primary">
                        {isRegistering ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                        쿠팡 일괄 등록
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
                                                    checked={selectedIds.includes(product.id)}
                                                    onChange={(e) => toggleSelect(product.id, e.target.checked)}
                                                />
                                            </td>
                                            <td className="p-4 align-middle">
                                                {product.processed_image_urls && product.processed_image_urls.length > 0 ? (
                                                    <img src={product.processed_image_urls[0]} alt={product.name} className="h-12 w-12 object-cover rounded-md border" />
                                                ) : (
                                                    <div className="h-12 w-12 bg-muted rounded-md border flex items-center justify-center text-xs text-muted-foreground">No img</div>
                                                )}
                                            </td>
                                            <td className="p-4 align-middle">
                                                <div className="font-medium line-clamp-1">{product.processed_name || product.name}</div>
                                                <div className="text-xs text-muted-foreground">{product.brand}</div>
                                            </td>
                                            <td className="p-4 align-middle">
                                                {product.selling_price?.toLocaleString()} 원
                                            </td>
                                            <td className="p-4 align-middle">
                                                <div className="flex flex-col gap-1">
                                                    {getStatusBadge(product)}
                                                    {product.market_listings && product.market_listings.length > 0 && (
                                                        <span className="text-[10px] text-muted-foreground">Coupang Linked</span>
                                                    )}
                                                </div>
                                            </td>
                                            <td className="p-4 align-middle text-right">
                                                <div className="flex justify-end gap-2">
                                                    {product.market_listings && product.market_listings.length > 0 && (
                                                        <Button size="icon" variant="ghost" onClick={() => handleSyncStatus(product.id)} title="상태 동기화">
                                                            <RefreshCcw className="h-4 w-4" />
                                                        </Button>
                                                    )}
                                                    <Button size="sm" variant="outline" onClick={() => router.push(`/products/${product.id}`)}>
                                                        수정
                                                    </Button>
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
