"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { MarketProduct } from "@/types";
import { Loader2, RefreshCw, RefreshCcw, AlertTriangle, Trash2, Ban } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Table, TableColumn, exportToCSV } from "@/components/ui/Table";
import { Input } from "@/components/ui/Input";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { Drawer } from "@/components/ui/Drawer";
import { Download } from "lucide-react";

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
    const [searchQuery, setSearchQuery] = useState("");
    const [currentPage, setCurrentPage] = useState(1);
    const [selectedProduct, setSelectedProduct] = useState<MarketProduct | null>(null);
    const itemsPerPage = 50;

    const filteredProducts = products.filter(product =>
        (product.name || product.processedName)?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        product.marketItemId?.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const paginatedProducts = filteredProducts.slice(
        (currentPage - 1) * itemsPerPage,
        currentPage * itemsPerPage
    );

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
            setSelectedIds([]);
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
            return <Badge variant="success" weight="solid">판매중</Badge>;
        }
        if (["SUSPENDED", "STOPPED", "OUT_OF_STOCK"].includes(listingStatus)) {
            return <Badge variant="warning" weight="solid">판매중지</Badge>;
        }
        if (listingStatus === "ACTIVE") return <Badge variant="success" weight="solid">판매중</Badge>;
        if (listingStatus === "SUSPENDED") return <Badge variant="warning" weight="solid">판매중지</Badge>;
        return <Badge variant="secondary">{product.status}</Badge>;
    };

    const getCoupangStatusBadge = (product: MarketProduct) => {
        const cpStatus = normalizeCoupangStatus(product.coupangStatus);
        if (!cpStatus) return null;

        if (cpStatus === 'DENIED') return <Badge variant="destructive" weight="solid">반려</Badge>;
        if (cpStatus === 'DELETED') return <Badge variant="destructive" weight="solid">삭제</Badge>;
        if (cpStatus === 'IN_REVIEW') return <Badge variant="info">심사중</Badge>;
        if (cpStatus === 'APPROVING') return <Badge variant="info">승인대기</Badge>;
        if (cpStatus === 'SAVED') return <Badge variant="secondary">임시저장</Badge>;
        if (cpStatus === 'PARTIAL_APPROVED') return <Badge variant="success">부분승인</Badge>;
        if (cpStatus === 'APPROVED') return <Badge variant="success">승인</Badge>;
        return <Badge variant="secondary">{cpStatus}</Badge>;
    };

    const getActiveListing = (product: MarketProduct) => product.marketItemId ? product : undefined;

    const columns: TableColumn<MarketProduct>[] = [
        {
            key: "select",
            title: "",
            width: "40px",
            render: (_, row) => (
                <input
                    type="checkbox"
                    className="h-3 w-3 rounded border-border"
                    checked={selectedIds.includes(row.marketItemId)}
                    onChange={(e) => toggleSelect(row.marketItemId, e.target.checked)}
                />
            ),
        },
        {
            key: "image",
            title: "이미지",
            width: "60px",
            render: (_, row) => (
                row.processedImageUrls && row.processedImageUrls.length > 0 ? (
                    <div className="h-8 w-8 rounded-sm border border-border overflow-hidden relative">
                        <Image
                            src={row.processedImageUrls[0]}
                            alt={row.name || "상품 이미지"}
                            fill
                            sizes="32px"
                            className="object-cover"
                        />
                    </div>
                ) : (
                    <div className="h-8 w-8 bg-muted rounded-sm border border-border flex items-center justify-center text-[9px] text-muted-foreground">No img</div>
                )
            ),
        },
        {
            key: "name",
            title: "상품명",
            width: "30%",
            render: (_, row) => (
                <div>
                    <div className="text-xs font-medium truncate">{row.processedName || row.name}</div>
                    <div className="text-[10px] text-muted-foreground truncate">{row.marketItemId}</div>
                </div>
            ),
        },
        {
            key: "sellingPrice",
            title: "가격",
            align: "right",
            width: "10%",
            render: (value) => (
                <span className="text-xs font-medium">{value?.toLocaleString()} 원</span>
            ),
        },
        {
            key: "status",
            title: "상태",
            width: "15%",
            render: (_, row) => (
                <div className="flex flex-col gap-0.5">
                    {getStatusBadge(row)}
                    {getCoupangStatusBadge(row)}
                    {getActiveListing(row) && (
                        <span className="text-[9px] text-muted-foreground">Coupang Linked</span>
                    )}
                </div>
            ),
        },
        {
            key: "actions",
            title: "작업",
            align: "right",
            width: "25%",
            render: (_, row) => {
                const activeListing = getActiveListing(row);
                return (
                    <div className="flex justify-end gap-1">
                        {activeListing && (
                            <>
                                {row.productId && (
                                    <>
                                        <Button size="icon" variant="ghost" onClick={() => handleSyncStatus(row.productId!)} title="상태 동기화" className="h-6 w-6">
                                            <RefreshCcw className="h-3 w-3" />
                                        </Button>
                                        <Button size="icon" variant="ghost" onClick={() => handleUpdateCoupang(row.productId!)} title="쿠팡 수정" className="h-6 w-6">
                                            <RefreshCw className="h-3 w-3" />
                                        </Button>
                                    </>
                                )}
                                <Button size="icon" variant="ghost" onClick={() => handleStopSales(row.marketItemId)} title="판매중지" className="h-6 w-6">
                                    <AlertTriangle className="h-3 w-3" />
                                </Button>
                                <Button size="icon" variant="ghost" onClick={() => handleDeleteCoupang(row.marketItemId)} title="삭제" className="h-6 w-6">
                                    <Trash2 className="h-3 w-3" />
                                </Button>
                            </>
                        )}
                        {row.productId && (
                            <Button size="xs" variant="outline" onClick={() => router.push(`/products/${row.productId}`)}>
                                수정
                            </Button>
                        )}
                    </div>
                );
            },
        },
    ];

    const totalPages = Math.ceil(filteredProducts.length / itemsPerPage);

    return (
        <div className="space-y-3">
            {/* Breadcrumb */}
            <Breadcrumb
                items={[
                    { label: "상품 관리" }
                ]}
            />

            {/* Toolbar */}
            <div className="flex items-center justify-between px-3 py-2 border border-border bg-card rounded-sm">
                <div className="flex items-center gap-2 flex-1">
                    <Input
                        type="text"
                        placeholder="상품명 또는 ID 검색..."
                        value={searchQuery}
                        onChange={(e) => {
                            setSearchQuery(e.target.value);
                            setCurrentPage(1);
                        }}
                        className="max-w-xs"
                        size="sm"
                    />
                    <div className="text-[10px] text-muted-foreground bg-muted px-2 py-1 rounded-sm">
                        총 {filteredProducts.length}개
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Button onClick={handleBulkRegister} disabled={loading || isRegistering} size="sm" variant="primary">
                        {isRegistering ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> : null}
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
                        size="sm"
                    >
                        <RefreshCcw className={`mr-1.5 h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
                        쿠팡 동기화
                    </Button>
                    <Button onClick={handleBulkUpdate} disabled={loading || bulkAction !== null} variant="outline" size="sm">
                        {bulkAction === "update" ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> : <RefreshCw className="mr-1.5 h-3 w-3" />}
                        일괄 수정
                    </Button>
                    <Button onClick={handleBulkStopSales} disabled={loading || bulkAction !== null} variant="outline" size="sm">
                        {bulkAction === "stop" ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> : <Ban className="mr-1.5 h-3 w-3" />}
                        판매중지
                    </Button>
                    <Button onClick={handleBulkDelete} disabled={loading || bulkAction !== null} variant="outline" size="sm">
                        {bulkAction === "delete" ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> : <Trash2 className="mr-1.5 h-3 w-3" />}
                        삭제
                    </Button>
                    <Button onClick={fetchProducts} disabled={loading} variant="outline" size="sm">
                        <RefreshCw className={`mr-1.5 h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
                        새로고침
                    </Button>
                    <Button
                        onClick={() => exportToCSV(filteredProducts, columns.filter(c => c.key !== 'select' && c.key !== 'image' && c.key !== 'actions'), 'MarketProducts')}
                        disabled={loading || filteredProducts.length === 0}
                        variant="outline"
                        size="sm"
                    >
                        <Download className="mr-1.5 h-3 w-3" />
                        CSV 다운로드
                    </Button>
                </div>
            </div>

            {/* Table */}
            <div className="border border-border rounded-sm bg-card">
                <div className="px-3 py-1.5 border-b border-border bg-muted/50">
                    <span className="text-[11px] font-semibold text-foreground">등록 상품 관리</span>
                </div>
                <div className="p-2">
                    <Table
                        columns={columns}
                        data={paginatedProducts}
                        loading={loading}
                        compact={true}
                        striped={true}
                        hover={true}
                        emptyMessage="등록된 상품이 없습니다."
                        onRowClick={(row) => setSelectedProduct(row)}
                        className="cursor-pointer"
                    />
                </div>
            </div>

            {/* Product Detail Drawer */}
            <Drawer
                isOpen={!!selectedProduct}
                onClose={() => setSelectedProduct(null)}
                title="상품 상세 정보"
                description={selectedProduct?.processedName || selectedProduct?.name || undefined}
                size="lg"
                footer={
                    <div className="flex justify-end gap-2">
                        <Button variant="outline" onClick={() => setSelectedProduct(null)}>닫기</Button>
                        {selectedProduct?.productId && (
                            <Button variant="primary" onClick={() => router.push(`/products/${selectedProduct.productId}`)}>편집 페이지로 이동</Button>
                        )}
                    </div>
                }
            >
                {selectedProduct && (
                    <div className="space-y-6">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1">
                                <span className="text-[10px] font-bold text-muted-foreground uppercase">마켓 상품 ID</span>
                                <p className="text-sm font-semibold">{selectedProduct.marketItemId}</p>
                            </div>
                            <div className="space-y-1">
                                <span className="text-[10px] font-bold text-muted-foreground uppercase">내부 상품 ID</span>
                                <p className="text-sm font-semibold">{selectedProduct.productId || "None"}</p>
                            </div>
                            <div className="space-y-1">
                                <span className="text-[10px] font-bold text-muted-foreground uppercase">판매 가격</span>
                                <p className="text-sm font-semibold text-primary">{selectedProduct.sellingPrice?.toLocaleString()} 원</p>
                            </div>
                            <div className="space-y-1">
                                <span className="text-[10px] font-bold text-muted-foreground uppercase">상태</span>
                                <div className="flex gap-2">
                                    {getStatusBadge(selectedProduct)}
                                    {getCoupangStatusBadge(selectedProduct)}
                                </div>
                            </div>
                        </div>

                        <div className="space-y-2">
                            <span className="text-[10px] font-bold text-muted-foreground uppercase">상품 이미지</span>
                            <div className="grid grid-cols-4 gap-2">
                                {selectedProduct.processedImageUrls?.map((url, i) => (
                                    <div key={i} className="aspect-square rounded-lg border border-border overflow-hidden relative">
                                        <Image src={url} alt={`Image ${i}`} fill className="object-cover" />
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="space-y-2">
                            <span className="text-[10px] font-bold text-muted-foreground uppercase">원본 데이터 (JSON)</span>
                            <pre className="p-4 bg-muted rounded-lg text-[10px] font-mono overflow-auto max-h-[300px]">
                                {JSON.stringify(selectedProduct, null, 2)}
                            </pre>
                        </div>
                    </div>
                )}
            </Drawer>

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="flex items-center justify-between px-4 py-2 border-t border-border bg-card">
                    <div className="text-[10px] text-muted-foreground">
                        {(currentPage - 1) * itemsPerPage + 1} - {Math.min(currentPage * itemsPerPage, filteredProducts.length)} / {filteredProducts.length}
                    </div>
                    <div className="flex items-center gap-1">
                        <Button
                            variant="outline"
                            size="xs"
                            onClick={() => setCurrentPage(1)}
                            disabled={currentPage === 1}
                        >
                            처음
                        </Button>
                        <Button
                            variant="outline"
                            size="xs"
                            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                            disabled={currentPage === 1}
                        >
                            이전
                        </Button>
                        <span className="px-2 text-[10px] font-medium">
                            {currentPage} / {totalPages}
                        </span>
                        <Button
                            variant="outline"
                            size="xs"
                            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                            disabled={currentPage === totalPages}
                        >
                            다음
                        </Button>
                        <Button
                            variant="outline"
                            size="xs"
                            onClick={() => setCurrentPage(totalPages)}
                            disabled={currentPage === totalPages}
                        >
                            마지막
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
}
