"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { Product } from "@/types";
import { Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";

export default function ProductListPage() {
    const router = useRouter();
    const [products, setProducts] = useState<Product[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchProducts = async () => {
        setLoading(true);
        try {
            const response = await api.get("/products/");
            setProducts(response.data);
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

    const getStatusBadge = (status: string) => {
        switch (status) {
            case 'COMPLETED': return <Badge variant="success">완료</Badge>;
            case 'FAILED': return <Badge variant="destructive">실패</Badge>;
            case 'PROCESSING': return <Badge variant="warning">처리중</Badge>;
            default: return <Badge variant="secondary">{status}</Badge>;
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <h1 className="text-3xl font-bold tracking-tight">상품 목록</h1>
                <Button onClick={fetchProducts} disabled={loading} variant="outline">
                    <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    새로고침
                </Button>
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
                                        <td colSpan={5} className="h-24 text-center">
                                            <Loader2 className="mx-auto h-6 w-6 animate-spin text-muted-foreground" />
                                        </td>
                                    </tr>
                                ) : products.length === 0 ? (
                                    <tr>
                                        <td colSpan={5} className="h-24 text-center text-muted-foreground">
                                            등록된 상품이 없습니다.
                                        </td>
                                    </tr>
                                ) : (
                                    products.map((product) => (
                                        <tr key={product.id} className="border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted">
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
                                                {getStatusBadge(product.processing_status)}
                                            </td>
                                            <td className="p-4 align-middle text-right">
                                                <div className="flex justify-end gap-2">
                                                    <Button size="sm" variant="ghost" onClick={() => handleRegister(product.id)}>
                                                        등록
                                                    </Button>
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
