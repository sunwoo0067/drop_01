"use client";

import { useEffect, useState, useMemo } from "react";
import Image from "next/image";
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
    AlertTriangle,
    ExternalLink,
    Trash2,
    Image as ImageIcon
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Table, TableColumn } from "@/components/ui/Table";
import { Drawer } from "@/components/ui/Drawer";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
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
    if (su === "APPROVAL_REQUESTED") return "APPROVING";
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

function isRegistrationSkipped(reason?: any): boolean {
    if (!reason) return false;
    const ctx = String(reason?.context || "").toLowerCase();
    if (ctx === "registration_skip") return true;
    const msg = String(reason?.message || reason?.reason || "");
    return msg.startsWith("SKIPPED:");
}

function formatSkipReason(reason?: any): string {
    const msg = String(reason?.message || reason?.reason || "");
    return msg.replace(/^SKIPPED:\s*/i, "").trim() || "상세 사유 없음";
}

export default function RegistrationPage() {
    const [items, setItems] = useState<RegistrationProduct[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState("");
    const [registeringIds, setRegisteringIds] = useState<Set<string>>(new Set());
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
    const [bulkRegistering, setBulkRegistering] = useState(false);
    const [selectedProduct, setSelectedProduct] = useState<RegistrationProduct | null>(null);

    const fetchProducts = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await api.get("/products/", {
                params: {
                    processingStatus: "COMPLETED",
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

    const handleRegister = async (productId: string) => {
        if (registeringIds.has(productId)) return;

        setRegisteringIds(prev => new Set(prev).add(productId));
        try {
            await api.post(`/coupang/register/${productId}`, null, {
                params: { autoFix: true, wait: true }
            });
            setItems(prev => prev.filter(item => item.id !== productId));
            setSelectedIds(prev => {
                const next = new Set(prev);
                next.delete(productId);
                return next;
            });
            if (selectedProduct?.id === productId) setSelectedProduct(null);
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

            setItems(prev => prev.map(item => {
                if (item.id === productId) {
                    return { ...item, coupangStatus: newStatus };
                }
                return item;
            }));

            if (selectedProduct?.id === productId) {
                setSelectedProduct(prev => prev ? { ...prev, coupangStatus: newStatus } : null);
            }

            if (newStatus === 'APPROVED') {
                alert("상품이 승인되었습니다! 목록에서 제거합니다.");
                setItems(prev => prev.filter(item => item.id !== productId));
                if (selectedProduct?.id === productId) setSelectedProduct(null);
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

    const filteredItems = useMemo(() => {
        return items.filter(item =>
            item.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
            item.processed_name?.toLowerCase().includes(searchTerm.toLowerCase())
        );
    }, [items, searchTerm]);

    const readyCount = useMemo(() => filteredItems.filter(i => i.imagesCount >= 1).length, [filteredItems]);

    const getMarketStatusBadge = (item: RegistrationProduct) => {
        if (isRegistrationSkipped(item.rejectionReason)) {
            return <Badge variant="outline" className="bg-amber-500/10 text-amber-600 border-amber-200">등록 제외</Badge>;
        }
        const status = normalizeCoupangStatus(item.coupangStatus);
        switch (status) {
            case 'DENIED': return <Badge variant="destructive" className="bg-destructive/10 text-destructive border-destructive/20 animate-pulse">심사 반려</Badge>;
            case 'IN_REVIEW':
            case 'APPROVING': return <Badge variant="outline" className="bg-blue-500/10 text-blue-600 border-blue-200">심사 중</Badge>;
            case 'APPROVED': return <Badge variant="outline" className="bg-emerald-500/10 text-emerald-600 border-emerald-200">승인 완료</Badge>;
            case 'SAVED': return <Badge variant="outline" className="bg-muted text-muted-foreground border-border">임시 저장</Badge>;
            default: return <Badge variant="outline" className="bg-muted/50 text-muted-foreground/60 border-border/50">{item.imagesCount >= 1 ? "등록 가능" : "준비 부족"}</Badge>;
        }
    };

    const columns: TableColumn<RegistrationProduct>[] = [
        {
            key: "selection",
            title: "선택",
            width: "50px",
            align: "center",
            render: (_, row) => (
                <input
                    type="checkbox"
                    checked={selectedIds.has(row.id)}
                    onChange={(e) => {
                        const checked = e.target.checked;
                        setSelectedIds(prev => {
                            const next = new Set(prev);
                            if (checked) next.add(row.id);
                            else next.delete(row.id);
                            return next;
                        });
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className="h-4 w-4 rounded border-border"
                />
            )
        },
        {
            key: "image",
            title: "이미지",
            width: "80px",
            render: (_, row) => (
                <div className="h-10 w-10 rounded-lg overflow-hidden bg-muted relative">
                    {row.processed_image_urls && row.processed_image_urls.length > 0 ? (
                        <Image src={row.processed_image_urls[0]} alt={row.name} fill className="object-cover" />
                    ) : (
                        <ImageIcon className="h-4 w-4 m-auto absolute inset-0 text-muted-foreground/30" />
                    )}
                </div>
            )
        },
        {
            key: "name",
            title: "상품명",
            render: (_, row) => (
                <div className="flex flex-col max-w-[400px]">
                    <div className="flex items-center gap-2">
                        <span className="font-bold truncate text-foreground/90">{row.processed_name || row.name}</span>
                        {row.forbiddenTags && row.forbiddenTags.length > 0 && (
                            <Badge className="bg-amber-500/10 text-amber-600 border-amber-200 text-[9px] h-4 px-1">태그주의</Badge>
                        )}
                    </div>
                    {row.processed_name && (
                        <span className="text-[10px] text-muted-foreground/60 truncate italic">{row.name}</span>
                    )}
                </div>
            )
        },
        {
            key: "coupang_status",
            title: "쿠팡 상태",
            width: "120px",
            render: (_, row) => getMarketStatusBadge(row)
        },
        {
            key: "selling_price",
            title: "판매가",
            width: "120px",
            align: "right",
            render: (price) => <span className="font-mono font-bold text-primary">{price.toLocaleString()}원</span>
        },
        {
            key: "actions",
            title: "작업",
            width: "150px",
            align: "right",
            render: (_, row) => {
                const isRegistering = registeringIds.has(row.id);
                const isReady = row.imagesCount >= 1;
                return (
                    <Button
                        size="sm"
                        variant={isReady ? "primary" : "outline"}
                        className="h-8 rounded-lg px-3 text-[11px] font-bold"
                        onClick={(e) => {
                            e.stopPropagation();
                            handleRegister(row.id);
                        }}
                        disabled={!isReady || isRegistering}
                    >
                        {isRegistering ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                        ) : normalizeCoupangStatus(row.coupangStatus) === 'DENIED' ? (
                            "재수정 및 등록"
                        ) : (
                            "등록 실행"
                        )}
                    </Button>
                );
            }
        }
    ];

    return (
        <div className="space-y-4 animate-in fade-in duration-500 pb-10">
            {/* Header Section */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 px-3 py-2 border border-border bg-card/50 backdrop-blur-sm rounded-sm">
                <Breadcrumb items={[{ label: "상품 등록 센터", icon: <Upload className="h-3 w-3" /> }]} />
                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={fetchProducts} className="rounded-lg h-9 px-4 font-bold">
                        <RotateCw className="mr-2 h-3.5 w-3.5" />
                        새로고침
                    </Button>
                    <Button variant="outline" size="sm" onClick={handleResetPending} className="rounded-lg h-9 px-4 font-bold border-destructive/20 text-destructive hover:bg-destructive/5">
                        <Trash2 className="mr-2 h-3.5 w-3.5" />
                        대기열 비우기
                    </Button>
                    <Button
                        size="sm"
                        onClick={handleBulkRegister}
                        disabled={selectedIds.size === 0 || bulkRegistering}
                        className="rounded-lg h-9 px-4 font-bold shadow-lg shadow-primary/20"
                    >
                        {bulkRegistering ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <Sparkles className="mr-2 h-3.5 w-3.5" />}
                        선택 상품 등록 ({selectedIds.size})
                    </Button>
                </div>
            </div>

            {/* Stats Overview */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {[
                    { label: "총 대기 상품", value: filteredItems.length, icon: ShoppingCart },
                    { label: "등록 가능", value: readyCount, icon: CheckCircle2, color: "text-emerald-500" },
                    { label: "이미지 부족", value: filteredItems.length - readyCount, icon: AlertCircle, color: "text-amber-500" },
                    { label: "선택된 상품", value: selectedIds.size, icon: MousePointer2, color: "text-primary" }
                ].map((stat, idx) => (
                    <Card key={idx} className="bg-card/40 border border-border pb-3 pt-4 px-4 shadow-sm relative overflow-hidden group">
                        <stat.icon className={cn("absolute -right-2 -bottom-2 h-12 w-12 opacity-5 group-hover:scale-110 transition-transform", stat.color)} />
                        <p className="text-[10px] font-black text-muted-foreground uppercase tracking-widest">{stat.label}</p>
                        <p className={cn("text-2xl font-black mt-1", stat.color)}>{stat.value}</p>
                    </Card>
                ))}
            </div>

            {/* Toolbar */}
            <div className="flex items-center gap-3 bg-card border border-border p-2 rounded-sm pr-4">
                <div className="relative flex-1 group">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
                    <Input
                        placeholder="등록 대기 상품 검색..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="pl-10 h-10 bg-transparent border-none focus-visible:ring-0 focus-visible:ring-offset-0 text-sm font-medium"
                    />
                </div>
                <div className="h-6 w-px bg-border mx-2" />
                <Button
                    variant="ghost"
                    size="sm"
                    className="text-[10px] font-black uppercase tracking-widest"
                    onClick={() => {
                        if (selectedIds.size === readyCount) setSelectedIds(new Set());
                        else setSelectedIds(new Set(filteredItems.filter(i => i.imagesCount >= 1).map(i => i.id)));
                    }}
                >
                    {selectedIds.size === readyCount ? "선택 해제" : "등록 가능 전체 선택"}
                </Button>
            </div>

            {/* Table */}
            <div className="border border-border/50 rounded-sm bg-card shadow-sm overflow-hidden">
                <Table
                    columns={columns}
                    data={filteredItems}
                    loading={loading}
                    hover
                    onRowClick={(row) => setSelectedProduct(row)}
                    emptyMessage="등록할 수 있는 가공 완료 상품이 없습니다."
                />
            </div>

            {/* Detail Drawer */}
            <Drawer
                isOpen={!!selectedProduct}
                onClose={() => setSelectedProduct(null)}
                title="등록 상세 정보"
                description="마켓 등록 상태와 반려 사유를 정밀 분석합니다."
                size="lg"
                footer={
                    <div className="flex items-center justify-between w-full">
                        <Button
                            variant="outline"
                            className="rounded-xl font-bold"
                            onClick={() => selectedProduct && handleSyncStatus(selectedProduct.id)}
                        >
                            <RefreshCcw className="mr-2 h-4 w-4" />
                            상태 재동기화
                        </Button>
                        <div className="flex items-center gap-2">
                            <Button variant="outline" onClick={() => setSelectedProduct(null)} className="rounded-xl font-bold">
                                닫기
                            </Button>
                            <Button
                                className="rounded-xl font-bold px-6 shadow-lg shadow-primary/20"
                                onClick={() => selectedProduct && handleRegister(selectedProduct.id)}
                                disabled={selectedProduct?.imagesCount === 0 || registeringIds.has(selectedProduct?.id || "")}
                            >
                                <Upload className="mr-2 h-4 w-4" />
                                즉시 재등록
                            </Button>
                        </div>
                    </div>
                }
            >
                {selectedProduct && (
                    <div className="space-y-8 pb-10">
                        {/* Status Analysis Header */}
                        <div className={cn(
                            "p-6 rounded-3xl border shadow-sm flex flex-col items-center text-center space-y-3",
                            normalizeCoupangStatus(selectedProduct.coupangStatus) === 'DENIED' ? "bg-destructive/5 border-destructive/20" : "bg-primary/5 border-primary/10"
                        )}>
                            <div className={cn(
                                "h-12 w-12 rounded-2xl flex items-center justify-center shadow-lg",
                                normalizeCoupangStatus(selectedProduct.coupangStatus) === 'DENIED' ? "bg-destructive text-white" : "bg-primary text-white"
                            )}>
                                {normalizeCoupangStatus(selectedProduct.coupangStatus) === 'DENIED' ? <AlertTriangle className="h-6 w-6" /> : <Clock className="h-6 w-6" />}
                            </div>
                            <div>
                                <h3 className="text-lg font-black tracking-tight">
                                    {isRegistrationSkipped(selectedProduct.rejectionReason) ? "등록 프로세스 제외" :
                                        normalizeCoupangStatus(selectedProduct.coupangStatus) === 'DENIED' ? "승인 반려됨" : "등록 대기 또는 심사 중"}
                                </h3>
                                <p className="text-xs text-muted-foreground mt-1 font-medium">쿠팡 파트너스 센터의 응답 결과입니다.</p>
                            </div>
                        </div>

                        {/* Rejection / Info Section */}
                        {(selectedProduct.rejectionReason || (selectedProduct.forbiddenTags && selectedProduct.forbiddenTags.length > 0)) && (
                            <div className="space-y-4">
                                <label className="text-[10px] font-black text-muted-foreground uppercase tracking-widest pl-1">Issue Overview</label>

                                {isRegistrationSkipped(selectedProduct.rejectionReason) && (
                                    <div className="p-5 rounded-2xl bg-amber-500/10 border border-amber-500/20">
                                        <div className="flex items-center gap-2 text-amber-600 mb-2">
                                            <AlertCircle className="h-4 w-4" />
                                            <span className="text-sm font-black">제외 사유</span>
                                        </div>
                                        <p className="text-[13px] text-amber-700 font-medium leading-relaxed">
                                            {formatSkipReason(selectedProduct.rejectionReason)}
                                        </p>
                                    </div>
                                )}

                                {normalizeCoupangStatus(selectedProduct.coupangStatus) === 'DENIED' && selectedProduct.rejectionReason && (
                                    <div className="p-5 rounded-2xl bg-destructive/5 border border-destructive/10">
                                        <div className="flex items-center gap-2 text-destructive mb-2">
                                            <AlertTriangle className="h-4 w-4" />
                                            <span className="text-sm font-black">심사 반려 사유 (쿠팡)</span>
                                        </div>
                                        <p className="text-[13px] text-destructive/80 font-medium leading-relaxed bg-white/50 p-4 rounded-xl border border-destructive/5">
                                            {selectedProduct.rejectionReason.reason || "상세 사유가 제공되지 않았습니다."}
                                        </p>
                                        {selectedProduct.rejectionReason.context && (
                                            <p className="text-[11px] text-muted-foreground mt-3 italic">
                                                Context: {selectedProduct.rejectionReason.context}
                                            </p>
                                        )}
                                    </div>
                                )}

                                {selectedProduct.forbiddenTags && selectedProduct.forbiddenTags.length > 0 && (
                                    <div className="p-5 rounded-2xl bg-amber-500/5 border border-amber-500/10">
                                        <div className="flex items-center gap-2 text-amber-600 mb-2">
                                            <Sparkles className="h-4 w-4" />
                                            <span className="text-sm font-black">금지 태그 감지</span>
                                        </div>
                                        <div className="flex flex-wrap gap-2 mt-2">
                                            {selectedProduct.forbiddenTags.map((tag, idx) => (
                                                <Badge key={idx} variant="outline" className="border-amber-500/20 text-amber-700 bg-amber-500/5">
                                                    {tag}
                                                </Badge>
                                            ))}
                                        </div>
                                        <p className="text-[11px] text-muted-foreground mt-3">위 태그들은 쿠팡 정책상 반려될 가능성이 높습니다. 수정 후 재등록을 권장합니다.</p>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Product Summary */}
                        <div className="grid grid-cols-2 gap-6">
                            <div className="space-y-3">
                                <label className="text-[10px] font-black text-muted-foreground uppercase tracking-widest pl-1">Product Identity</label>
                                <div className="aspect-[4/3] relative rounded-2xl overflow-hidden border border-border group shadow-inner bg-muted">
                                    {selectedProduct.processed_image_urls?.[0] ? (
                                        <Image src={selectedProduct.processed_image_urls[0]} alt="Thumbnail" fill className="object-cover transition-transform group-hover:scale-105" />
                                    ) : <ImageIcon className="h-8 w-8 m-auto text-muted-foreground/20" />}
                                    <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent flex flex-col justify-end p-4">
                                        <p className="text-white font-black truncate">{selectedProduct.processed_name || selectedProduct.name}</p>
                                        <p className="text-white/60 text-[10px] truncate">{selectedProduct.id}</p>
                                    </div>
                                </div>
                            </div>

                            <div className="space-y-6">
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-muted-foreground uppercase tracking-widest pl-1">Pricing & Logic</label>
                                    <div className="p-4 rounded-2xl bg-muted/30 border border-border">
                                        <p className="text-[10px] text-muted-foreground font-black uppercase mb-1">Final Selling Price</p>
                                        <p className="text-2xl font-black text-primary font-mono">{selectedProduct.selling_price.toLocaleString()}원</p>
                                    </div>
                                </div>
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-muted-foreground uppercase tracking-widest pl-1">Asset Status</label>
                                    <div className="p-4 rounded-2xl bg-muted/30 border border-border flex items-center justify-between">
                                        <div>
                                            <p className="text-[10px] text-muted-foreground font-black uppercase mb-1">Processed Images</p>
                                            <p className="text-lg font-black">{selectedProduct.imagesCount} / 1</p>
                                        </div>
                                        <div className={cn(
                                            "h-8 w-8 rounded-full flex items-center justify-center shadow-inner",
                                            selectedProduct.imagesCount >= 1 ? "bg-emerald-500 shadow-emerald-500/20" : "bg-destructive shadow-destructive/20"
                                        )}>
                                            {selectedProduct.imagesCount >= 1 ? <CheckCircle2 className="h-4 w-4 text-white" /> : <AlertCircle className="h-4 w-4 text-white" />}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </Drawer>
        </div>
    );
}

// Missing imports for some icons used in stats
import { MousePointer2 } from "lucide-react";
