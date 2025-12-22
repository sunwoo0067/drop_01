"use client";

import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

interface OrderSyncFailure {
    id: string;
    endpoint: string;
    httpStatus?: number | null;
    errorMessage?: string | null;
    fetchedAt?: string | null;
    requestPayload?: Record<string, any> | null;
    responsePayload?: Record<string, any> | null;
}

interface MappingIssueReport {
    total: number;
    counts: Record<string, number>;
    samples: Array<{
        orderId: string;
        reason: string;
        sellerProductId?: string | null;
    }>;
}

interface ImageValidationReport {
    counts: Record<string, number>;
}

interface SchedulerState {
    name: string;
    status: string;
    updatedAt: string;
    meta?: Record<string, any> | null;
}

interface ImageValidationFailure {
    url: string;
    reason: string;
    size: string;
    width: string;
    height: string;
}

export default function OrderSyncPage() {
    const [failures, setFailures] = useState<OrderSyncFailure[]>([]);
    const [loading, setLoading] = useState(false);
    const [retryLoading, setRetryLoading] = useState(false);
    const [selectedIds, setSelectedIds] = useState<string[]>([]);
    const [mappingReport, setMappingReport] = useState<MappingIssueReport | null>(null);
    const [filterEndpoint, setFilterEndpoint] = useState("");
    const [filterError, setFilterError] = useState("");
    const [imageReport, setImageReport] = useState<ImageValidationReport | null>(null);
    const [schedulerState, setSchedulerState] = useState<SchedulerState[]>([]);
    const [imageFailures, setImageFailures] = useState<ImageValidationFailure[]>([]);

    const fetchFailures = useCallback(async () => {
        setLoading(true);
        try {
            const res = await api.get<OrderSyncFailure[]>("/coupang/orders/sync-failures", {
                params: { limit: 200, offset: 0 },
            });
            setFailures(res.data || []);
        } catch (err) {
            console.error("Failed to fetch sync failures", err);
        } finally {
            setLoading(false);
        }
    }, []);

    const fetchMappingReport = useCallback(async () => {
        try {
            const res = await api.get<MappingIssueReport>("/coupang/orders/mapping-issues", {
                params: { limit: 200 },
            });
            setMappingReport(res.data || null);
        } catch (err) {
            console.error("Failed to fetch mapping issues", err);
        }
    }, []);

    const fetchImageReport = useCallback(async () => {
        try {
            const res = await api.get<ImageValidationReport>("/products/image-validation-report");
            setImageReport(res.data || null);
        } catch (err) {
            console.error("Failed to fetch image validation report", err);
        }
    }, []);

    const fetchImageFailures = useCallback(async () => {
        try {
            const res = await api.get<ImageValidationFailure[]>("/products/image-validation-failures", {
                params: { limit: 50 },
            });
            setImageFailures(res.data || []);
        } catch (err) {
            console.error("Failed to fetch image validation failures", err);
        }
    }, []);

    const fetchSchedulerState = useCallback(async () => {
        try {
            const res = await api.get<SchedulerState[]>("/coupang/orders/scheduler-state");
            setSchedulerState(res.data || []);
        } catch (err) {
            console.error("Failed to fetch scheduler state", err);
        }
    }, []);

    const handleRetry = async () => {
        setRetryLoading(true);
        try {
            await api.post("/coupang/orders/sync-ownerclan-invoices", {
                limit: 0,
                dryRun: false,
                retryCount: 1,
            });
        } catch (err) {
            console.error("Failed to trigger retry", err);
        } finally {
            setRetryLoading(false);
        }
    };

    const handleRetrySelected = async () => {
        if (selectedIds.length === 0) {
            return;
        }
        setRetryLoading(true);
        try {
            await api.post("/coupang/orders/sync-failures/retry", {
                ids: selectedIds,
                retryCount: 1,
            });
            await fetchFailures();
            setSelectedIds([]);
        } catch (err) {
            console.error("Failed to retry selected failures", err);
        } finally {
            setRetryLoading(false);
        }
    };

    const toggleSelection = (id: string) => {
        setSelectedIds((prev) =>
            prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
        );
    };

    useEffect(() => {
        fetchFailures();
        fetchMappingReport();
        fetchImageReport();
        fetchSchedulerState();
        fetchImageFailures();
    }, [fetchFailures, fetchMappingReport, fetchImageReport, fetchSchedulerState, fetchImageFailures]);

    const filteredFailures = failures.filter((item) => {
        if (filterEndpoint && !item.endpoint.toLowerCase().includes(filterEndpoint.toLowerCase())) {
            return false;
        }
        if (filterError && !(item.errorMessage || "").toLowerCase().includes(filterError.toLowerCase())) {
            return false;
        }
        return true;
    });

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold">주문 동기화 실패</h1>
                    <p className="text-sm text-muted-foreground">오너클랜 송장/취소 → 쿠팡 반영 실패 목록</p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" onClick={fetchFailures} isLoading={loading}>
                        새로고침
                    </Button>
                    <Button variant="outline" onClick={fetchMappingReport}>
                        매핑 점검
                    </Button>
                    <Button variant="outline" onClick={fetchImageReport}>
                        이미지 리포트
                    </Button>
                    <Button variant="outline" onClick={fetchImageFailures}>
                        이미지 실패 상세
                    </Button>
                    <Button variant="outline" onClick={fetchSchedulerState}>
                        스케줄 상태
                    </Button>
                    <Button variant="outline" onClick={handleRetrySelected} isLoading={retryLoading} disabled={selectedIds.length === 0}>
                        선택 재시도
                    </Button>
                    <Button onClick={handleRetry} isLoading={retryLoading}>
                        전체 재시도
                    </Button>
                </div>
            </div>

            <Card>
                <CardContent className="py-4">
                    <div className="grid gap-3 md:grid-cols-2">
                        <div>
                            <div className="mb-1 text-xs text-muted-foreground">Endpoint</div>
                            <Input
                                value={filterEndpoint}
                                onChange={(e) => setFilterEndpoint(e.target.value)}
                                placeholder="upload_invoices, cancel_order..."
                            />
                        </div>
                        <div>
                            <div className="mb-1 text-xs text-muted-foreground">Error</div>
                            <Input
                                value={filterError}
                                onChange={(e) => setFilterError(e.target.value)}
                                placeholder="오류 메시지 검색"
                            />
                        </div>
                    </div>
                </CardContent>
            </Card>

            {filteredFailures.length === 0 ? (
                <Card>
                    <CardContent className="py-10 text-center text-sm text-muted-foreground">
                        실패 로그가 없습니다.
                    </CardContent>
                </Card>
            ) : (
                <div className="grid gap-4">
                    {filteredFailures.map((item) => (
                        <Card key={item.id}>
                            <CardHeader className="pb-3">
                                <div className="flex items-center gap-3">
                                    <input
                                        type="checkbox"
                                        className="h-4 w-4 accent-primary"
                                        checked={selectedIds.includes(item.id)}
                                        onChange={() => toggleSelection(item.id)}
                                    />
                                    <CardTitle className="text-base">{item.endpoint}</CardTitle>
                                </div>
                                <div className="text-xs text-muted-foreground">
                                    HTTP {item.httpStatus ?? "-"} · {item.fetchedAt ?? "-"}
                                </div>
                            </CardHeader>
                            <CardContent className="space-y-3 text-sm">
                                <div className="text-destructive">
                                    {item.errorMessage || "Unknown error"}
                                </div>
                                {item.requestPayload && (
                                    <details className="rounded-md border p-3">
                                        <summary className="cursor-pointer text-xs font-medium">요청 Payload</summary>
                                        <pre className="mt-2 whitespace-pre-wrap text-xs">
                                            {JSON.stringify(item.requestPayload, null, 2)}
                                        </pre>
                                    </details>
                                )}
                                {item.responsePayload && (
                                    <details className="rounded-md border p-3">
                                        <summary className="cursor-pointer text-xs font-medium">응답 Payload</summary>
                                        <pre className="mt-2 whitespace-pre-wrap text-xs">
                                            {JSON.stringify(item.responsePayload, null, 2)}
                                        </pre>
                                    </details>
                                )}
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}

            {mappingReport && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">주문 매핑 점검</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                        <div className="text-muted-foreground">최근 {mappingReport.total}건 기준</div>
                        <div className="flex flex-wrap gap-2">
                            {Object.entries(mappingReport.counts).length === 0 && (
                                <span className="text-xs text-muted-foreground">문제 없음</span>
                            )}
                            {Object.entries(mappingReport.counts).map(([key, value]) => (
                                <span key={key} className="rounded-full bg-accent/50 px-3 py-1 text-xs">
                                    {key}: {value}
                                </span>
                            ))}
                        </div>
                        {mappingReport.samples.length > 0 && (
                            <details className="rounded-md border p-3">
                                <summary className="cursor-pointer text-xs font-medium">샘플</summary>
                                <pre className="mt-2 whitespace-pre-wrap text-xs">
                                    {JSON.stringify(mappingReport.samples.slice(0, 20), null, 2)}
                                </pre>
                            </details>
                        )}
                    </CardContent>
                </Card>
            )}

            {imageReport && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">이미지 검증 리포트</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                        <div className="flex flex-wrap gap-2">
                            {Object.entries(imageReport.counts).length === 0 && (
                                <span className="text-xs text-muted-foreground">실패 로그 없음</span>
                            )}
                            {Object.entries(imageReport.counts).map(([key, value]) => (
                                <span key={key} className="rounded-full bg-accent/50 px-3 py-1 text-xs">
                                    {key}: {value}
                                </span>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            )}

            <Card>
                <CardHeader>
                    <CardTitle className="text-base">이미지 검증 실패 상세</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                    {imageFailures.length === 0 ? (
                        <div className="text-xs text-muted-foreground">실패 상세 없음</div>
                    ) : (
                        imageFailures.map((item, idx) => (
                            <div key={`${item.url}-${idx}`} className="rounded-md border px-3 py-2">
                                <div className="text-xs text-muted-foreground">{item.reason}</div>
                                <div className="truncate text-xs">{item.url}</div>
                                <div className="text-[10px] text-muted-foreground">
                                    size={item.size}, {item.width}x{item.height}
                                </div>
                            </div>
                        ))
                    )}
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle className="text-base">스케줄 상태</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                    {schedulerState.length === 0 ? (
                        <div className="text-xs text-muted-foreground">상태 정보 없음</div>
                    ) : (
                        schedulerState.map((item) => (
                            <div key={item.name} className="flex items-center justify-between rounded-md border px-3 py-2">
                                <div>
                                    <div className="font-medium">{item.name}</div>
                                    <div className="text-xs text-muted-foreground">{item.updatedAt}</div>
                                </div>
                                <div className="text-xs uppercase">{item.status}</div>
                            </div>
                        ))
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
