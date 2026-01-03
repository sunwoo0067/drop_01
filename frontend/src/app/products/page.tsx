"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { MarketProduct } from "@/types";
import { Loader2, RefreshCw, RefreshCcw, AlertTriangle, Trash2, Ban, MoreHorizontal, Settings, ChevronRight, Download, Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Table, TableColumn, exportToCSV } from "@/components/ui/Table";
import { Input } from "@/components/ui/Input";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { Drawer } from "@/components/ui/Drawer";
import { Select } from "@/components/ui/Select";

function normalizeCoupangStatus(status?: string | null): string | null {
    if (!status) return null;
    const s = String(status).trim();
    if (!s) return null;

    const su = s.toUpperCase();
    if (su === "APPROVAL_REQUESTED") return "APPROVING";
    if (["DENIED", "DELETED", "IN_REVIEW", "SAVED", "APPROVING", "APPROVED", "PARTIAL_APPROVED"].includes(su)) return su;

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
    const [bulkActionTarget, setBulkActionTarget] = useState<string>("default");
    const [searchQuery, setSearchQuery] = useState("");
    const [currentPage, setCurrentPage] = useState(1);
    const [selectedProduct, setSelectedProduct] = useState<MarketProduct | null>(null);
    const itemsPerPage = 50;

    const filteredProducts = products.filter(product =>
        (product.name || product.processedName)?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        product.marketItemId?.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const paginatedProducts = filteredProducts.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);
    const totalPages = Math.ceil(filteredProducts.length / itemsPerPage);

    const fetchProducts = async () => {
        setLoading(true);
        try {
            const response = await api.get("/market/products", { params: { limit: 200 } });
            const items = Array.isArray(response.data?.items) ? response.data.items : [];
            setProducts(items.length > 0 ? items : []);
            setSelectedIds([]);
        } catch (error) {
            console.error("Failed to fetch products", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchProducts(); }, []);

    const handleBulkRegister = async () => {
        if (!confirm(selectedIds.length === 0 ? "모든 '처리완료' 상품을 등록하시겠습니까?" : `선택된 ${selectedIds.length}개 상품을 쿠팡에 등록하시겠습니까?`)) return;
        setIsRegistering(true);
        try {
            const productIds = products.filter(p => selectedIds.includes(p.marketItemId)).map(p => p.productId).filter(Boolean);
            await api.post("/coupang/register/bulk", { productIds: selectedIds.length > 0 ? productIds : null });
            alert("대량 등록 작업이 시작되었습니다.");
            setSelectedIds([]);
            fetchProducts();
        } catch (error) { alert("대량 등록 요청 실패"); } finally { setIsRegistering(false); }
    };

    const handleBulkAction = async (action: string) => {
        if (action === "default") return;
        if (selectedIds.length === 0) { alert("상품을 선택해주세요."); return; }
        if (!confirm(`선택된 ${selectedIds.length}개 상품에 대해 작업을 수행하시겠습니까?`)) return;

        setLoading(true);
        try {
            const targets = products.filter(p => selectedIds.includes(p.marketItemId));
            if (action === "update") {
                await Promise.allSettled(targets.filter(p => p.productId).map(p => api.put(`/coupang/products/${p.productId}`)));
            } else if (action === "stop") {
                await Promise.allSettled(targets.map(p => api.post(`/coupang/products/${p.marketItemId}/stop-sales`)));
            } else if (action === "delete") {
                await Promise.allSettled(targets.map(p => api.delete(`/coupang/products/${p.marketItemId}`)));
            }
            alert("일괄 작업 완료");
            fetchProducts();
        } catch (error) { alert("작업 실패"); } finally { setLoading(false); setBulkActionTarget("default"); }
    };

    const handleSingleAction = async (action: 'sync' | 'update' | 'stop' | 'delete', productId: string, marketItemId?: string) => {
        try {
            if (action === 'sync') await api.post(`/coupang/sync-status/${productId}`);
            else if (action === 'update') await api.put(`/coupang/products/${productId}`);
            else if (action === 'stop') await api.post(`/coupang/products/${marketItemId}/stop-sales`);
            else if (action === 'delete') await api.delete(`/coupang/products/${marketItemId}`);
            alert("작업 성공");
            fetchProducts();
        } catch (e) { alert("작업 실패"); }
    };

    const getStatusBadge = (product: MarketProduct) => {
        const s = String(product.status || "").toUpperCase();
        if (["ON_SALE", "ONSALE", "SALE", "SELLING", "ACTIVE"].includes(s)) return <Badge variant="success" weight="solid" className="text-[9px]">판매중</Badge>;
        if (["SUSPENDED", "STOPPED", "OUT_OF_STOCK"].includes(s)) return <Badge variant="warning" weight="solid" className="text-[9px]">판매중지</Badge>;
        return <Badge variant="secondary" className="text-[9px]">{product.status}</Badge>;
    };

    const getCoupangStatusBadge = (product: MarketProduct) => {
        const cp = normalizeCoupangStatus(product.coupangStatus);
        if (!cp) return null;
        const variants: any = { DENIED: 'destructive', DELETED: 'destructive', IN_REVIEW: 'info', APPROVING: 'info', SAVED: 'secondary', PARTIAL_APPROVED: 'success', APPROVED: 'success' };
        const labels: any = { DENIED: '반려', DELETED: '삭제', IN_REVIEW: '심사중', APPROVING: '승인대기', SAVED: '임시저장', PARTIAL_APPROVED: '부분승인', APPROVED: '승인' };
        return <Badge variant={variants[cp] || 'secondary'} weight={['DENIED', 'DELETED', 'APPROVED'].includes(cp) ? 'solid' : 'outline'} className="text-[9px]">{labels[cp] || cp}</Badge>;
    };

    const columns: TableColumn<MarketProduct>[] = [
        {
            key: "select", title: "", width: "40px",
            render: (_, row) => (
                <input type="checkbox" className="h-3 w-3 rounded border-border" checked={selectedIds.includes(row.marketItemId)} onChange={(e) => {
                    if (e.target.checked) setSelectedIds(p => [...p, row.marketItemId]);
                    else setSelectedIds(p => p.filter(i => i !== row.marketItemId));
                }} />
            )
        },
        {
            key: "image", title: "이미지", width: "60px",
            render: (_, row) => (
                <div className="h-9 w-9 rounded-sm border border-border overflow-hidden relative bg-muted">
                    {row.processedImageUrls?.[0] ? <Image src={row.processedImageUrls[0]} alt="img" fill sizes="40px" className="object-cover" /> : null}
                </div>
            )
        },
        {
            key: "name", title: "상품 정보", width: "50%",
            render: (_, row) => (
                <div className="space-y-0.5">
                    <div className="text-[11px] font-bold leading-tight line-clamp-1">{row.processedName || row.name}</div>
                    <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                        <span className="font-mono">{row.marketItemId}</span>
                        {row.productId && <Badge variant="outline" className="text-[8px] h-3.5 px-1 py-0 border-primary/20 text-primary/70">Internal</Badge>}
                    </div>
                </div>
            )
        },
        {
            key: "price", title: "판매가", align: "right", width: "15%",
            render: (_, row) => <span className="text-[11px] font-black">{row.sellingPrice?.toLocaleString()}<span className="text-[9px] font-normal ml-0.5 text-muted-foreground">원</span></span>
        },
        {
            key: "status", title: "상태", width: "20%",
            render: (_, row) => (
                <div className="flex flex-wrap gap-1 items-center">
                    {getStatusBadge(row)}
                    {getCoupangStatusBadge(row)}
                </div>
            )
        },
        {
            key: "detail", title: "", width: "40px", align: "right",
            render: (_, row) => <ChevronRight className="h-4 w-4 text-muted-foreground/30" />
        }
    ];

    return (
        <div className="space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 px-3 py-2 border border-border bg-card rounded-sm shadow-sm">
                <Breadcrumb items={[{ label: "상품 관리" }]} />
                <div className="flex items-center gap-2">
                    <Select
                        value={bulkActionTarget}
                        onChange={(e) => handleBulkAction(e.target.value)}
                        className="h-8 text-[11px] w-32 font-medium"
                        options={[
                            { value: "default", label: "일괄 작업 선택" },
                            { value: "update", label: "일괄 수정 반영" },
                            { value: "stop", label: "일괄 판매중지" },
                            { value: "delete", label: "일괄 삭제" },
                        ]}
                    />
                    <Button onClick={handleBulkRegister} disabled={loading || isRegistering} size="sm" variant="primary" className="h-8 text-[11px] font-bold">
                        {isRegistering ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> : null}
                        쿠팡 등록
                    </Button>
                    <Button variant="outline" size="sm" className="h-8 w-8 p-0" onClick={() => fetchProducts()} disabled={loading}>
                        <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                    </Button>
                </div>
            </div>

            <div className="flex items-center gap-2 bg-card border border-border p-2 rounded-sm pr-4">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground opacity-50" />
                    <Input
                        placeholder="상품명 또는 마켓 ID 검색..."
                        value={searchQuery}
                        onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
                        className="pl-9 h-9 text-xs border-none bg-transparent focus-visible:ring-0"
                    />
                </div>
                <div className="h-4 w-px bg-border mx-2" />
                <span className="text-[10px] font-bold text-muted-foreground shrink-0 uppercase tracking-widest">Total: {filteredProducts.length}</span>
                <Button
                    variant="ghost"
                    size="xs"
                    className="ml-2 h-7 text-muted-foreground hover:text-primary"
                    onClick={() => exportToCSV(filteredProducts, columns.filter(c => !['select', 'image', 'detail'].includes(c.key)), 'MarketProducts')}
                >
                    <Download className="h-3.5 w-3.5 mr-1" />
                    CSV
                </Button>
            </div>

            <div className="border border-border/50 rounded-sm bg-card shadow-sm overflow-hidden">
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

            <Drawer
                isOpen={!!selectedProduct}
                onClose={() => setSelectedProduct(null)}
                title="상품 상세 정보"
                description={selectedProduct?.processedName || selectedProduct?.name || undefined}
                size="xl"
                footer={
                    <div className="flex justify-between items-center w-full">
                        <div className="flex gap-1.5">
                            {selectedProduct?.productId && (
                                <>
                                    <Button size="sm" variant="outline" onClick={() => handleSingleAction('sync', selectedProduct.productId!)} className="text-[11px]">상태 동기화</Button>
                                    <Button size="sm" variant="outline" onClick={() => handleSingleAction('update', selectedProduct.productId!)} className="text-[11px]">수정 반영</Button>
                                </>
                            )}
                            <Button size="sm" variant="outline" onClick={() => handleSingleAction('stop', '', selectedProduct?.marketItemId)} className="text-[11px] text-warning hover:bg-warning/10">판매중지</Button>
                            <Button size="sm" variant="outline" onClick={() => handleSingleAction('delete', '', selectedProduct?.marketItemId)} className="text-[11px] text-destructive hover:bg-destructive/10">삭제</Button>
                        </div>
                        <div className="flex gap-2">
                            <Button variant="ghost" size="sm" onClick={() => setSelectedProduct(null)}>닫기</Button>
                            {selectedProduct?.productId && (
                                <Button variant="primary" size="sm" onClick={() => router.push(`/products/${selectedProduct.productId}`)}>편집 페이지</Button>
                            )}
                        </div>
                    </div>
                }
            >
                {selectedProduct && (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                        <div className="space-y-4">
                            <div className="aspect-square relative rounded-xl border border-border overflow-hidden bg-muted group">
                                {selectedProduct.processedImageUrls?.[0] ? (
                                    <Image src={selectedProduct.processedImageUrls[0]} alt="main" fill className="object-cover" />
                                ) : <div className="flex items-center justify-center h-full text-muted-foreground">이미지 없음</div>}
                            </div>
                            <div className="grid grid-cols-4 gap-2">
                                {selectedProduct.processedImageUrls?.slice(1, 5).map((url, i) => (
                                    <div key={i} className="aspect-square rounded-lg border border-border overflow-hidden relative bg-muted">
                                        <Image src={url} alt={`sub ${i}`} fill className="object-cover" />
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div className="space-y-6">
                            <div className="space-y-2">
                                <div className="flex gap-2">
                                    {getStatusBadge(selectedProduct)}
                                    {getCoupangStatusBadge(selectedProduct)}
                                </div>
                                <h2 className="text-xl font-black leading-tight">{selectedProduct.processedName || selectedProduct.name}</h2>
                                <p className="text-xs text-muted-foreground font-mono">{selectedProduct.marketItemId}</p>
                            </div>

                            <div className="grid grid-cols-2 gap-4 py-4 border-y border-border/50">
                                <div className="space-y-1">
                                    <p className="text-[10px] font-bold text-muted-foreground uppercase">판매 가격</p>
                                    <p className="text-2xl font-black text-primary">{selectedProduct.sellingPrice?.toLocaleString()}원</p>
                                </div>
                                <div className="space-y-1">
                                    <p className="text-[10px] font-bold text-muted-foreground uppercase">배송 방식</p>
                                    <p className="text-sm font-bold">일반 택배 (CJ 대한통운)</p>
                                </div>
                            </div>

                            <div className="space-y-4">
                                <h4 className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">상세 설정 데이터</h4>
                                <div className="rounded-lg bg-muted/30 p-4 font-mono text-[10px] max-h-[300px] overflow-auto border border-border/50">
                                    <pre>{JSON.stringify(selectedProduct, null, 2)}</pre>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </Drawer>

            {totalPages > 1 && (
                <div className="flex items-center justify-between px-3 py-2 border border-border/50 bg-card rounded-sm shadow-sm">
                    <div className="text-[10px] text-muted-foreground font-medium">
                        Showing {(currentPage - 1) * itemsPerPage + 1} - {Math.min(currentPage * itemsPerPage, filteredProducts.length)} of {filteredProducts.length}
                    </div>
                    <div className="flex items-center gap-1">
                        <Button variant="ghost" size="xs" onClick={() => setCurrentPage(1)} disabled={currentPage === 1} className="h-7 w-7 p-0">«</Button>
                        <Button variant="ghost" size="xs" onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage === 1} className="h-7 px-2 text-[10px]">Prev</Button>
                        <div className="px-3 text-[10px] font-black text-primary border-x border-border mx-1">{currentPage} / {totalPages}</div>
                        <Button variant="ghost" size="xs" onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages} className="h-7 px-2 text-[10px]">Next</Button>
                        <Button variant="ghost" size="xs" onClick={() => setCurrentPage(totalPages)} disabled={currentPage === totalPages} className="h-7 w-7 p-0">»</Button>
                    </div>
                </div>
            )}
        </div>
    );
}
