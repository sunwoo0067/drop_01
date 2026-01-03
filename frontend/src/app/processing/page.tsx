"use client";

import { useEffect, useState, useMemo } from "react";
import Image from "next/image";
import {
    Loader2,
    Search,
    Wand2,
    CheckCircle2,
    Clock,
    XCircle,
    AlertCircle,
    RotateCw,
    ExternalLink,
    Sparkles,
    Trash2,
    Edit3,
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

export default function ProcessingPage() {
    const [items, setItems] = useState<Product[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState("");
    const [processingIds, setProcessingIds] = useState<Set<string>>(new Set());
    const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);

    const fetchProducts = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await api.get("/products/");
            setItems(Array.isArray(response.data) ? response.data : []);
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

    const handleProcess = async (productId: string) => {
        if (processingIds.has(productId)) return;

        setProcessingIds(prev => new Set(prev).add(productId));
        try {
            await api.post(`/products/${productId}/process`, {
                minImagesRequired: 1,
                forceFetchOwnerClan: false
            });
            // Refresh status after a short delay
            setTimeout(fetchProducts, 2000);
        } catch (e) {
            console.error("Processing failed", e);
            alert("가공 트리거 실패");
        } finally {
            setProcessingIds(prev => {
                const next = new Set(prev);
                next.delete(productId);
                return next;
            });
        }
    };

    const handleProcessPending = async () => {
        try {
            await api.post("/products/process/pending", null, {
                params: { limit: 10, minImagesRequired: 1 }
            });
            alert("대기 중인 상품들에 대해 가공이 시작되었습니다.");
            setTimeout(fetchProducts, 1000);
        } catch (e) {
            console.error("Batch processing failed", e);
        }
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case "COMPLETED": return <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-200 hover:bg-emerald-500/20">가공 완료</Badge>;
            case "PROCESSING": return <Badge className="bg-blue-500/10 text-blue-600 border-blue-200 animate-pulse">가공 중</Badge>;
            case "FAILED": return <Badge variant="destructive" className="bg-destructive/10 text-destructive border-destructive/20">가공 실패</Badge>;
            default: return <Badge variant="secondary" className="bg-muted text-muted-foreground">가공 대기</Badge>;
        }
    };

    const filteredItems = useMemo(() => {
        return items.filter(item =>
            item.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
            item.processed_name?.toLowerCase().includes(searchTerm.toLowerCase())
        );
    }, [items, searchTerm]);

    const columns: TableColumn<Product>[] = [
        {
            key: "image",
            title: "이미지",
            width: "80px",
            render: (_, row) => (
                <div className="h-10 w-10 rounded-lg overflow-hidden bg-muted relative">
                    {row.processed_image_urls && row.processed_image_urls.length > 0 ? (
                        <Image
                            src={row.processed_image_urls[0]}
                            alt={row.name}
                            fill
                            className="object-cover"
                        />
                    ) : (
                        <Wand2 className="h-4 w-4 m-auto absolute inset-0 text-muted-foreground/30" />
                    )}
                </div>
            )
        },
        {
            key: "name",
            title: "상품명",
            render: (_, row) => (
                <div className="flex flex-col max-w-[400px]">
                    <span className="font-bold truncate text-foreground/90">{row.processed_name || row.name}</span>
                    {row.processed_name && (
                        <span className="text-[10px] text-muted-foreground/60 line-through truncate">{row.name}</span>
                    )}
                </div>
            )
        },
        {
            key: "processing_status",
            title: "가공 상태",
            width: "120px",
            render: (status) => getStatusBadge(status)
        },
        {
            key: "selling_price",
            title: "판매가",
            width: "120px",
            align: "right",
            render: (price) => <span className="font-mono font-bold text-primary">{price.toLocaleString()}원</span>
        },
        {
            key: "images",
            title: "이미지 수",
            width: "100px",
            align: "center",
            render: (_, row) => (
                <div className="flex items-center gap-1.5 justify-center">
                    <ImageIcon className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs font-bold">{row.processed_image_urls?.length || 0}</span>
                </div>
            )
        },
        {
            key: "actions",
            title: "작업",
            width: "150px",
            align: "right",
            render: (_, row) => (
                <div className="flex items-center justify-end gap-2">
                    <Button
                        size="sm"
                        variant="accent"
                        className="h-8 rounded-lg px-3 text-[11px] font-bold"
                        onClick={(e) => {
                            e.stopPropagation();
                            handleProcess(row.id);
                        }}
                        disabled={processingIds.has(row.id) || row.processing_status === "PROCESSING"}
                    >
                        {processingIds.has(row.id) ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                        ) : row.processing_status === "COMPLETED" ? (
                            "재가공"
                        ) : (
                            "가공 시작"
                        )}
                    </Button>
                </div>
            )
        }
    ];

    return (
        <div className="space-y-4 animate-in fade-in duration-500">
            {/* Header Section */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 px-3 py-2 border border-border bg-card/50 backdrop-blur-sm rounded-sm">
                <Breadcrumb items={[{ label: "가공 센터", icon: <Wand2 className="h-3 w-3" /> }]} />
                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={fetchProducts} className="rounded-lg h-9 px-4 font-bold">
                        <RotateCw className="mr-2 h-3.5 w-3.5" />
                        새로고침
                    </Button>
                    <Button size="sm" onClick={handleProcessPending} className="rounded-lg h-9 px-4 font-bold shadow-lg shadow-primary/20">
                        <Sparkles className="mr-2 h-3.5 w-3.5" />
                        미가공 일괄 시작
                    </Button>
                </div>
            </div>

            {/* Toolbar */}
            <div className="flex items-center gap-3 bg-card border border-border p-2 rounded-sm pr-4">
                <div className="relative flex-1 group">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
                    <Input
                        placeholder="상품명 또는 키워드 검색..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="pl-10 h-10 bg-transparent border-none focus-visible:ring-0 focus-visible:ring-offset-0 text-sm font-medium"
                    />
                </div>
                <div className="h-6 w-px bg-border mx-2" />
                <span className="text-[10px] font-black text-muted-foreground shrink-0 uppercase tracking-[0.2em] opacity-60">
                    Total: <span className="text-foreground ml-1">{filteredItems.length}</span>
                </span>
            </div>

            {/* Table Container */}
            <div className="border border-border/50 rounded-sm bg-card shadow-sm overflow-hidden">
                <Table
                    columns={columns}
                    data={filteredItems}
                    loading={loading}
                    hover
                    onRowClick={(row) => setSelectedProduct(row)}
                    emptyMessage="가공 대상 상품이 없습니다. 소싱에서 상품을 승격시켜주세요."
                />
            </div>

            {/* Detail Drawer */}
            <Drawer
                isOpen={!!selectedProduct}
                onClose={() => setSelectedProduct(null)}
                title="상품 가공 상세"
                description="AI에 의해 최적화된 상품 정보를 확인하고 수정합니다."
                size="lg"
                footer={
                    <div className="flex items-center justify-between w-full">
                        <Button variant="outline" className="rounded-xl font-bold border-destructive/20 text-destructive hover:bg-destructive/10">
                            <Trash2 className="mr-2 h-4 w-4" />
                            가공 데이터 초기화
                        </Button>
                        <div className="flex items-center gap-2">
                            <Button variant="outline" onClick={() => setSelectedProduct(null)} className="rounded-xl font-bold">
                                닫기
                            </Button>
                            <Button className="rounded-xl font-bold px-6 shadow-lg shadow-primary/20" onClick={() => handleProcess(selectedProduct?.id || "")}>
                                <RotateCw className="mr-2 h-4 w-4" />
                                재가공 실행
                            </Button>
                        </div>
                    </div>
                }
            >
                {selectedProduct && (
                    <div className="space-y-8">
                        {/* Image Showcase */}
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                            {selectedProduct.processed_image_urls?.map((url, idx) => (
                                <div key={idx} className="aspect-square relative rounded-2xl overflow-hidden border border-border group">
                                    <Image src={url} alt={`Image ${idx}`} fill className="object-cover transition-transform group-hover:scale-110" />
                                    <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                                        <Button size="icon" variant="secondary" className="h-8 w-8 rounded-full">
                                            <ExternalLink className="h-4 w-4" />
                                        </Button>
                                    </div>
                                    {idx === 0 && (
                                        <Badge className="absolute top-2 left-2 bg-primary text-white text-[9px] uppercase font-black px-2">Representative</Badge>
                                    )}
                                </div>
                            )) || (
                                    <div className="col-span-full h-40 flex flex-col items-center justify-center border-2 border-dashed border-border rounded-2xl text-muted-foreground/30">
                                        <ImageIcon className="h-10 w-10 mb-2" />
                                        <p className="text-xs font-bold uppercase tracking-widest">No Images Available</p>
                                    </div>
                                )}
                        </div>

                        {/* Text Information */}
                        <div className="space-y-6">
                            <div className="space-y-2">
                                <label className="text-[10px] font-black text-muted-foreground uppercase tracking-widest">Optimized Name</label>
                                <div className="p-4 rounded-2xl bg-muted/30 border border-border flex items-center justify-between group">
                                    <span className="font-bold text-lg">{selectedProduct.processed_name || "미가공"}</span>
                                    <Button size="icon" variant="ghost" className="opacity-0 group-hover:opacity-100 transition-opacity">
                                        <Edit3 className="h-4 w-4" />
                                    </Button>
                                </div>
                                <div className="flex items-center gap-2 px-1">
                                    <span className="text-[10px] text-muted-foreground uppercase font-bold">Original:</span>
                                    <span className="text-[10px] text-muted-foreground/50 truncate italic">{selectedProduct.name}</span>
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-muted-foreground uppercase tracking-widest">Selling Price</label>
                                    <div className="p-4 rounded-2xl bg-muted/30 border border-border">
                                        <span className="font-mono font-black text-2xl text-primary">{selectedProduct.selling_price.toLocaleString()}원</span>
                                    </div>
                                </div>
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-muted-foreground uppercase tracking-widest">Status</label>
                                    <div className="p-4 rounded-2xl bg-muted/30 border border-border flex items-center gap-3">
                                        <div className={cn(
                                            "h-3 w-3 rounded-full shadow-sm",
                                            selectedProduct.processing_status === "COMPLETED" ? "bg-emerald-500 shadow-emerald-500/20" :
                                                selectedProduct.processing_status === "PROCESSING" ? "bg-blue-500 animate-pulse shadow-blue-500/20" : "bg-muted shadow-inner"
                                        )} />
                                        <span className="font-bold">{selectedProduct.processing_status}</span>
                                    </div>
                                </div>
                            </div>

                            <div className="space-y-2">
                                <label className="text-[10px] font-black text-muted-foreground uppercase tracking-widest">Keywords</label>
                                <div className="flex flex-wrap gap-2 p-4 rounded-2xl bg-muted/30 border border-border">
                                    {selectedProduct.processed_keywords?.map((kw, idx) => (
                                        <Badge key={idx} variant="secondary" className="bg-primary/5 text-primary border-primary/10 px-3 py-1 rounded-lg text-xs font-bold">
                                            #{kw}
                                        </Badge>
                                    )) || <p className="text-xs text-muted-foreground/50 italic">추출된 키워드가 없습니다.</p>}
                                    <Button size="icon" variant="outline" className="h-7 w-7 rounded-lg border-dashed">
                                        <Sparkles className="h-3 w-3 text-primary" />
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </Drawer>
        </div>
    );
}
