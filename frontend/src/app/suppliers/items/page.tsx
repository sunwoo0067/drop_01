"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";

type SupplierItemRawRow = {
    id: string;
    supplierCode: string;
    itemCode: string | null;
    itemKey: string | null;
    itemId: string | null;
    itemName: string | null;
    supplyPrice: number | null;
    sourceUpdatedAt: string | null;
    fetchedAt: string | null;
};

function formatDateTime(value: string | null | undefined): string {
    if (!value) return "-";
    try {
        return new Date(value).toLocaleString("ko-KR");
    } catch {
        return value;
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

function getErrorMessage(error: unknown): string {
    if (axios.isAxiosError(error)) {
        const detail = (error.response?.data as any)?.detail;
        if (typeof detail === "string" && detail) return detail;
        return error.message;
    }

    if (error instanceof Error) return error.message;
    return "알 수 없는 오류가 발생했습니다.";
}

export default function SupplierItemsPage() {
    const [query, setQuery] = useState("");
    const [offset, setOffset] = useState(0);
    const limit = 50;

    const queryRef = useRef(query);

    const [rows, setRows] = useState<SupplierItemRawRow[]>([]);
    const [loading, setLoading] = useState(false);

    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [detail, setDetail] = useState<any | null>(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [refreshLoading, setRefreshLoading] = useState(false);

    useEffect(() => {
        queryRef.current = query;
    }, [query]);

    const fetchRows = useCallback(
        async (targetOffset?: number) => {
            const nextOffset = targetOffset ?? offset;
            setLoading(true);
            try {
                const res = await api.get<SupplierItemRawRow[]>("/suppliers/ownerclan/raw/items", {
                    params: {
                        q: queryRef.current || undefined,
                        limit,
                        offset: nextOffset,
                    },
                });
                setRows(res.data);
            } catch (e) {
                console.error(e);
                alert(getErrorMessage(e));
            } finally {
                setLoading(false);
            }
        },
        [limit, offset]
    );

    const fetchDetail = useCallback(async (id: string) => {
        setSelectedId(id);
        setDetail(null);
        setDetailLoading(true);
        try {
            const res = await api.get(`/suppliers/ownerclan/raw/items/${id}`);
            setDetail(res.data);
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
            setSelectedId(null);
        } finally {
            setDetailLoading(false);
        }
    }, []);

    const refreshFromOwnerClan = useCallback(async () => {
        const itemCode = (detail?.itemCode ?? detail?.raw?.item_code ?? detail?.raw?.itemCode ?? "") as string;
        if (!itemCode || typeof itemCode !== "string") {
            alert("itemCode를 찾을 수 없습니다.");
            return;
        }

        if (!confirm("오너클랜에서 원본을 다시 조회하여 갱신하시겠습니까?")) return;

        setRefreshLoading(true);
        try {
            await api.post("/suppliers/ownerclan/items/import", { itemCode });
            if (selectedId) {
                await fetchDetail(selectedId);
            }
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setRefreshLoading(false);
        }
    }, [detail, fetchDetail, selectedId]);

    useEffect(() => {
        fetchRows();
    }, [fetchRows]);

    return (
        <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <h1 className="text-3xl font-bold tracking-tight">공급사 상품 목록</h1>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        disabled={loading}
                        onClick={() => {
                            if (offset === 0) {
                                fetchRows(0);
                            } else {
                                setOffset(0);
                            }
                        }}
                    >
                        새로고침
                    </Button>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Card>
                    <CardHeader>
                        <CardTitle>오너클랜 상품(Raw)</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="flex flex-col gap-3">
                            <div className="flex flex-col sm:flex-row gap-2">
                                <Input
                                    placeholder="상품명/상품코드 검색"
                                    value={query}
                                    onChange={(e) => setQuery(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter") {
                                            setSelectedId(null);
                                            setDetail(null);

                                            if (offset === 0) {
                                                fetchRows(0);
                                            } else {
                                                setOffset(0);
                                            }
                                        }
                                    }}
                                />
                                <div className="flex gap-2">
                                    <Button
                                        variant="outline"
                                        disabled={loading}
                                        onClick={() => {
                                            setSelectedId(null);
                                            setDetail(null);

                                            if (offset === 0) {
                                                fetchRows(0);
                                            } else {
                                                setOffset(0);
                                            }
                                        }}
                                    >
                                        검색
                                    </Button>
                                    <Button variant="outline" disabled={loading} onClick={() => fetchRows()}>
                                        새로고침
                                    </Button>
                                </div>
                            </div>

                            <div className="flex items-center gap-2">
                                <Button
                                    variant="outline"
                                    disabled={loading || offset === 0}
                                    onClick={() => {
                                        setSelectedId(null);
                                        setDetail(null);
                                        setOffset((prev) => Math.max(0, prev - limit));
                                    }}
                                >
                                    이전
                                </Button>
                                <Button
                                    variant="outline"
                                    disabled={loading || rows.length < limit}
                                    onClick={() => {
                                        setSelectedId(null);
                                        setDetail(null);
                                        setOffset((prev) => prev + limit);
                                    }}
                                >
                                    다음
                                </Button>
                                <div className="text-sm text-muted-foreground">offset: {offset}</div>
                            </div>

                            <div className="overflow-x-auto rounded-md border">
                                <table className="w-full caption-bottom text-sm text-left">
                                    <thead className="[&_tr]:border-b">
                                        <tr className="border-b">
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground">itemCode</th>
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground">상품명</th>
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground">공급가</th>
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground">수집</th>
                                        </tr>
                                    </thead>
                                    <tbody className="[&_tr:last-child]:border-0">
                                        {loading && rows.length === 0 ? (
                                            <tr>
                                                <td colSpan={4} className="h-24 text-center text-muted-foreground">
                                                    불러오는 중...
                                                </td>
                                            </tr>
                                        ) : rows.length === 0 ? (
                                            <tr>
                                                <td colSpan={4} className="h-24 text-center text-muted-foreground">
                                                    데이터가 없습니다.
                                                </td>
                                            </tr>
                                        ) : (
                                            rows.map((row) => (
                                                <tr
                                                    key={row.id}
                                                    className={`border-b transition-colors hover:bg-muted/50 cursor-pointer ${
                                                        selectedId === row.id ? "bg-muted/50" : ""
                                                    }`}
                                                    onClick={() => fetchDetail(row.id)}
                                                >
                                                    <td className="p-4 align-middle">
                                                        <div className="font-medium">{row.itemCode ?? "-"}</div>
                                                        <div className="text-xs text-muted-foreground">{row.id}</div>
                                                    </td>
                                                    <td className="p-4 align-middle">
                                                        <div className="font-medium">{row.itemName ?? "-"}</div>
                                                        <div className="text-xs text-muted-foreground">{row.itemKey ?? "-"}</div>
                                                    </td>
                                                    <td className="p-4 align-middle">{formatPrice(row.supplyPrice)}</td>
                                                    <td className="p-4 align-middle">{formatDateTime(row.fetchedAt)}</td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>

                            <div className="text-xs text-muted-foreground">
                                현재는 오너클랜 Raw 상품만 표시합니다. (향후 다른 공급사 확장 시 supplierCode 필터를 추가할 수 있습니다.)
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <div className="flex items-center justify-between gap-2">
                            <CardTitle>상세(Raw)</CardTitle>
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={!selectedId}
                                    onClick={() => {
                                        if (!selectedId) return;
                                        window.open(`/suppliers/items/${selectedId}`, "_blank", "noopener,noreferrer");
                                    }}
                                >
                                    새 창으로 보기
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    isLoading={refreshLoading}
                                    disabled={!selectedId || detailLoading || refreshLoading || !detail}
                                    onClick={refreshFromOwnerClan}
                                >
                                    원본 다시 불러오기
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={!selectedId && !detail}
                                    onClick={() => {
                                        setSelectedId(null);
                                        setDetail(null);
                                    }}
                                >
                                    닫기
                                </Button>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent>
                        {detailLoading ? (
                            <div className="text-sm text-muted-foreground">불러오는 중...</div>
                        ) : !selectedId ? (
                            <div className="text-sm text-muted-foreground">목록에서 상품을 선택해 주세요.</div>
                        ) : !detail ? (
                            <div className="text-sm text-muted-foreground">상세 데이터가 없습니다.</div>
                        ) : (
                            (() => {
                                const raw = (detail.raw ?? detail) as any;
                                const itemCode = raw?.item_code ?? raw?.itemCode ?? detail.itemCode;
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
                                    <div className="space-y-4">
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
                                                <div className="font-medium">
                                                    {supplyPrice !== undefined ? formatPrice(Number(supplyPrice)) : "-"}
                                                </div>
                                            </div>
                                            <div className="rounded-md border p-3">
                                                <div className="text-xs text-muted-foreground">재고</div>
                                                <div className="font-medium">{formatNumber(stock)}</div>
                                            </div>
                                            <div className="rounded-md border p-3">
                                                <div className="text-xs text-muted-foreground">상태</div>
                                                <div className="font-medium">
                                                    {status ? <Badge variant="secondary">{String(status)}</Badge> : "-"}
                                                </div>
                                            </div>
                                        </div>

                                        <div className="space-y-1">
                                            <div className="text-xs text-muted-foreground">카테고리</div>
                                            <div className="text-sm break-words">{category ? String(category) : "-"}</div>
                                        </div>

                                        <div className="space-y-2">
                                            <div className="text-sm font-medium">이미지</div>
                                            {images.length === 0 ? (
                                                <div className="text-sm text-muted-foreground">-</div>
                                            ) : (
                                                <div className="grid grid-cols-3 gap-2">
                                                    {images.slice(0, 9).map((url: any, idx: number) => (
                                                        <div key={`${idx}-${String(url)}`} className="rounded-md border overflow-hidden bg-muted/20">
                                                            <img
                                                                src={String(url)}
                                                                alt={typeof itemName === "string" ? itemName : "image"}
                                                                className="h-24 w-full object-cover"
                                                            />
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>

                                        <div className="space-y-2">
                                            <div className="text-sm font-medium">상품 설명</div>
                                            {descriptionStr ? (
                                                looksLikeHtml ? (
                                                    <iframe
                                                        className="w-full h-64 rounded-md border bg-white"
                                                        sandbox=""
                                                        srcDoc={descriptionStr}
                                                        title="description"
                                                    />
                                                ) : (
                                                    <div className="rounded-md border bg-muted/20 p-3 overflow-auto max-h-[260px]">
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
                                );
                            })()
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
