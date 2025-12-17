"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import axios from "axios";
import api from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";

function formatNumber(value: any): string {
    if (value === null || value === undefined) return "-";
    try {
        const n = typeof value === "number" ? value : Number(value);
        if (Number.isFinite(n)) return n.toLocaleString();
        return String(value);
    } catch {
        return String(value);
    }
}

function formatPrice(value: number | null | undefined): string {
    if (value === null || value === undefined) return "-";
    try {
        return `${value.toLocaleString()} 원`;
    } catch {
        return `${value} 원`;
    }
}

function getErrorMessage(error: unknown): string {
    if (axios.isAxiosError(error)) {
        const detail = (error.response?.data as any)?.detail;
        if (typeof detail === "string" && detail) return detail;
        return error.message;
    }

    if (error instanceof Error) return error.message;
    return "알 수 없는 오류가 발생했습니다.";
}

export default function SupplierItemDetailPage() {
    const router = useRouter();
    const params = useParams();
    const id = String((params as any)?.id ?? "");

    const [detail, setDetail] = useState<any | null>(null);
    const [loading, setLoading] = useState(false);
    const [refreshLoading, setRefreshLoading] = useState(false);

    const fetchDetail = useCallback(async () => {
        if (!id) return;
        setLoading(true);
        try {
            const res = await api.get(`/suppliers/ownerclan/raw/items/${id}`);
            setDetail(res.data);
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchDetail();
    }, [fetchDetail]);

    const refreshFromOwnerClan = useCallback(async () => {
        const raw = (detail?.raw ?? detail) as any;
        const itemCode = (detail?.itemCode ?? raw?.item_code ?? raw?.itemCode ?? "") as string;
        if (!itemCode || typeof itemCode !== "string") {
            alert("itemCode를 찾을 수 없습니다.");
            return;
        }

        if (!confirm("오너클랜에서 원본을 다시 조회하여 갱신하시겠습니까?")) return;

        setRefreshLoading(true);
        try {
            await api.post("/suppliers/ownerclan/items/import", { itemCode });
            await fetchDetail();
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setRefreshLoading(false);
        }
    }, [detail, fetchDetail]);

    const raw = (detail?.raw ?? detail) as any;
    const itemCode = raw?.item_code ?? raw?.itemCode ?? detail?.itemCode;
    const itemName = raw?.item_name ?? raw?.itemName ?? raw?.name;
    const price = raw?.price;
    const supplyPrice = raw?.supply_price ?? raw?.supplyPrice;
    const stock = raw?.stock;
    const category = raw?.category;
    const status = raw?.status;
    const images =
        (Array.isArray(raw?.images) && raw.images) ||
        (Array.isArray(raw?.image_urls) && raw.image_urls) ||
        (Array.isArray(raw?.imageUrls) && raw.imageUrls) ||
        [];
    const description = raw?.description ?? raw?.content;
    const options = Array.isArray(raw?.options) ? raw.options : [];
    const descriptionStr = typeof description === "string" ? description : description ? JSON.stringify(description, null, 2) : "";
    const looksLikeHtml = typeof description === "string" && /<\w+[\s>]/.test(description);

    return (
        <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                <div className="space-y-1">
                    <h1 className="text-2xl font-bold tracking-tight">공급사 상품 상세</h1>
                    <div className="text-sm text-muted-foreground break-words">{id}</div>
                </div>
                <div className="flex items-center gap-2">
                    <Button variant="outline" onClick={() => router.back()}>
                        뒤로
                    </Button>
                    <Button variant="outline" disabled={loading} onClick={fetchDetail}>
                        새로고침
                    </Button>
                    <Button variant="outline" isLoading={refreshLoading} disabled={loading || refreshLoading || !detail} onClick={refreshFromOwnerClan}>
                        원본 다시 불러오기
                    </Button>
                </div>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>오너클랜 상품</CardTitle>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="text-sm text-muted-foreground">불러오는 중...</div>
                    ) : !detail ? (
                        <div className="text-sm text-muted-foreground">상세 데이터가 없습니다.</div>
                    ) : (
                        <div className="space-y-6">
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                <div className="space-y-3">
                                    <div className="space-y-1">
                                        <div className="text-xs text-muted-foreground">상품코드</div>
                                        <div className="text-base font-semibold break-words">{itemCode ?? "-"}</div>
                                    </div>

                                    <div className="space-y-1">
                                        <div className="text-xs text-muted-foreground">상품명</div>
                                        <div className="text-lg font-bold leading-snug break-words">{itemName ?? "-"}</div>
                                    </div>

                                    <div className="grid grid-cols-2 gap-3">
                                        <div className="rounded-md border p-3">
                                            <div className="text-xs text-muted-foreground">판매가</div>
                                            <div className="font-medium">{price !== undefined ? formatPrice(Number(price)) : "-"}</div>
                                        </div>
                                        <div className="rounded-md border p-3">
                                            <div className="text-xs text-muted-foreground">공급가</div>
                                            <div className="font-medium">{supplyPrice !== undefined ? formatPrice(Number(supplyPrice)) : "-"}</div>
                                        </div>
                                        <div className="rounded-md border p-3">
                                            <div className="text-xs text-muted-foreground">재고</div>
                                            <div className="font-medium">{formatNumber(stock)}</div>
                                        </div>
                                        <div className="rounded-md border p-3">
                                            <div className="text-xs text-muted-foreground">상태</div>
                                            <div className="font-medium">{status ? <Badge variant="secondary">{String(status)}</Badge> : "-"}</div>
                                        </div>
                                    </div>

                                    <div className="space-y-1">
                                        <div className="text-xs text-muted-foreground">카테고리</div>
                                        <div className="text-sm break-words">{category ? String(category) : "-"}</div>
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <div className="text-sm font-medium">이미지</div>
                                    {images.length === 0 ? (
                                        <div className="text-sm text-muted-foreground">-</div>
                                    ) : (
                                        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-2 xl:grid-cols-3 gap-2">
                                            {images.slice(0, 12).map((url: any, idx: number) => (
                                                <a
                                                    key={`${idx}-${String(url)}`}
                                                    href={String(url)}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    className="rounded-md border overflow-hidden bg-muted/20"
                                                >
                                                    <img
                                                        src={String(url)}
                                                        alt={typeof itemName === "string" ? itemName : "image"}
                                                        className="h-40 w-full object-cover"
                                                    />
                                                </a>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>

                            <div className="space-y-2">
                                <div className="text-sm font-medium">상품 설명</div>
                                {descriptionStr ? (
                                    looksLikeHtml ? (
                                        <iframe className="w-full h-[520px] rounded-md border bg-white" sandbox="" srcDoc={descriptionStr} title="description" />
                                    ) : (
                                        <div className="rounded-md border bg-muted/20 p-3 overflow-auto max-h-[520px]">
                                            <pre className="text-xs whitespace-pre-wrap break-words">{descriptionStr}</pre>
                                        </div>
                                    )
                                ) : (
                                    <div className="text-sm text-muted-foreground">-</div>
                                )}
                            </div>

                            <div className="space-y-2">
                                <div className="text-sm font-medium">옵션</div>
                                {options.length === 0 ? (
                                    <div className="text-sm text-muted-foreground">-</div>
                                ) : (
                                    <div className="overflow-x-auto rounded-md border">
                                        <table className="w-full caption-bottom text-sm text-left">
                                            <thead className="[&_tr]:border-b">
                                                <tr className="border-b">
                                                    <th className="h-10 px-3 align-middle font-medium text-muted-foreground">name</th>
                                                    <th className="h-10 px-3 align-middle font-medium text-muted-foreground">value</th>
                                                </tr>
                                            </thead>
                                            <tbody className="[&_tr:last-child]:border-0">
                                                {options.map((opt: any, idx: number) => (
                                                    <tr key={idx} className="border-b">
                                                        <td className="p-3 align-middle">{String(opt?.name ?? opt?.option_name ?? opt?.key ?? "-")}</td>
                                                        <td className="p-3 align-middle">{String(opt?.value ?? opt?.option_value ?? opt?.val ?? "-")}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </div>

                            <details className="rounded-md border bg-muted/10 p-3">
                                <summary className="cursor-pointer text-sm font-medium">원본 JSON 보기</summary>
                                <div className="mt-3 overflow-auto max-h-[520px]">
                                    <pre className="text-xs whitespace-pre-wrap break-words">{JSON.stringify(raw, null, 2)}</pre>
                                </div>
                            </details>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
