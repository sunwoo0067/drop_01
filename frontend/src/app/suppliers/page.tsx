"use client";

import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import api from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";

type OwnerClanStatus = {
    configured: boolean;
    account: null | {
        id: string;
        supplierCode: string;
        userType: string;
        username: string;
        tokenExpiresAt: string | null;
        isPrimary: boolean;
        isActive: boolean;
        updatedAt: string | null;
    };
};

type OwnerClanAccount = {
    id: string;
    supplierCode: string;
    userType: string;
    username: string;
    tokenExpiresAt: string | null;
    isPrimary: boolean;
    isActive: boolean;
    updatedAt: string | null;
};

type SupplierSyncJob = {
    id: string;
    supplierCode: string;
    jobType: string;
    status: string;
    progress: number;
    lastError: string | null;
    params: Record<string, any>;
    startedAt: string | null;
    finishedAt: string | null;
    createdAt: string | null;
    updatedAt: string | null;
};

type OwnerClanRawType = "items" | "orders" | "qna" | "categories";

type OwnerClanItemRawRow = {
    id: string;
    supplierCode: string;
    itemCode: string | null;
    itemKey: string | null;
    itemId: string | null;
    sourceUpdatedAt: string | null;
    fetchedAt: string | null;
};

type OwnerClanOrderRawRow = {
    id: string;
    supplierCode: string;
    accountId: string;
    orderId: string;
    fetchedAt: string | null;
};

type OwnerClanQnaRawRow = {
    id: string;
    supplierCode: string;
    accountId: string;
    qnaId: string;
    fetchedAt: string | null;
};

type OwnerClanCategoryRawRow = {
    id: string;
    supplierCode: string;
    categoryId: string;
    fetchedAt: string | null;
};

const rawEndpointMap: Record<OwnerClanRawType, string> = {
    items: "/suppliers/ownerclan/raw/items",
    orders: "/suppliers/ownerclan/raw/orders",
    qna: "/suppliers/ownerclan/raw/qna",
    categories: "/suppliers/ownerclan/raw/categories",
};

function getRawLabel(type: OwnerClanRawType): string {
    switch (type) {
        case "items":
            return "상품(items)";
        case "orders":
            return "주문(orders)";
        case "qna":
            return "QnA";
        case "categories":
            return "카테고리";
        default:
            return type;
    }
}

function formatDateTime(value: string | null | undefined): string {
    if (!value) return "-";
    try {
        return new Date(value).toLocaleString("ko-KR");
    } catch {
        return value;
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

function getStatusBadge(status: string) {
    switch (status) {
        case "queued":
            return <Badge variant="secondary">대기</Badge>;
        case "running":
            return <Badge variant="warning">실행중</Badge>;
        case "succeeded":
            return <Badge variant="success">성공</Badge>;
        case "failed":
            return <Badge variant="destructive">실패</Badge>;
        default:
            return <Badge variant="outline">{status}</Badge>;
    }
}

function getJobLabel(jobType: string): string {
    switch (jobType) {
        case "ownerclan_items_raw":
            return "상품(items)";
        case "ownerclan_orders_raw":
            return "주문(orders)";
        case "ownerclan_qna_raw":
            return "QnA";
        case "ownerclan_categories_raw":
            return "카테고리";
        default:
            return jobType;
    }
}

export default function SuppliersPage() {
    const [ownerClanStatus, setOwnerClanStatus] = useState<OwnerClanStatus | null>(null);
    const [loadingStatus, setLoadingStatus] = useState(false);
    const [ownerClanAccounts, setOwnerClanAccounts] = useState<OwnerClanAccount[]>([]);

    const [jobs, setJobs] = useState<SupplierSyncJob[]>([]);
    const [jobsLoading, setJobsLoading] = useState(false);

    const [triggerLoading, setTriggerLoading] = useState<string | null>(null);
    const [itemDatePreset, setItemDatePreset] = useState<"1d" | "3d" | "7d" | "30d" | "all">("7d");
    const [rawType, setRawType] = useState<OwnerClanRawType>("items");
    const [rawQuery, setRawQuery] = useState("");
    const [rawOffset, setRawOffset] = useState(0);
    const rawLimit = 50;
    const [rawRows, setRawRows] = useState<
        OwnerClanItemRawRow[] | OwnerClanOrderRawRow[] | OwnerClanQnaRawRow[] | OwnerClanCategoryRawRow[]
    >([]);
    const [rawLoading, setRawLoading] = useState(false);
    const [rawSelectedId, setRawSelectedId] = useState<string | null>(null);
    const [rawDetail, setRawDetail] = useState<any | null>(null);
    const [rawDetailLoading, setRawDetailLoading] = useState(false);

    const canTrigger = !!ownerClanStatus?.configured;

    const runningJobIds = useMemo(() => new Set(jobs.filter((j) => j.status === "queued" || j.status === "running").map((j) => j.id)), [jobs]);

    const fetchOwnerClanStatus = async () => {
        setLoadingStatus(true);
        try {
            const res = await api.get<OwnerClanStatus>("/settings/suppliers/ownerclan/primary");
            setOwnerClanStatus(res.data);
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setLoadingStatus(false);
        }
    };

    const fetchOwnerClanAccounts = async () => {
        try {
            const res = await api.get<OwnerClanAccount[]>("/settings/suppliers/ownerclan/accounts");
            setOwnerClanAccounts(res.data);
        } catch (e) {
            // vendor 계정은 선택사항이라 실패해도 화면은 동작해야 함
            console.error(e);
        }
    };

    const fetchJobs = async () => {
        setJobsLoading(true);
        try {
            const res = await api.get<SupplierSyncJob[]>("/suppliers/sync/jobs", { params: { supplierCode: "ownerclan", limit: 50 } });
            setJobs(res.data);
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setJobsLoading(false);
        }
    };

    const fetchRawRows = async (targetOffset?: number) => {
        const offset = targetOffset ?? rawOffset;
        setRawLoading(true);
        try {
            const res = await api.get(rawEndpointMap[rawType], {
                params: {
                    q: rawQuery || undefined,
                    limit: rawLimit,
                    offset,
                },
            });
            setRawRows(res.data);
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setRawLoading(false);
        }
    };

    const fetchRawDetail = async (id: string) => {
        setRawDetailLoading(true);
        try {
            const res = await api.get(`${rawEndpointMap[rawType]}/${id}`);
            setRawDetail(res.data);
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setRawDetailLoading(false);
        }
    };

    const changeRawType = (type: OwnerClanRawType) => {
        setRawType(type);
        setRawOffset(0);
        setRawSelectedId(null);
        setRawDetail(null);
    };

    useEffect(() => {
        fetchOwnerClanStatus();
        fetchOwnerClanAccounts();
        fetchJobs();
    }, []);

    useEffect(() => {
        if (runningJobIds.size === 0) return;

        const timer = setInterval(() => {
            fetchJobs();
        }, 2500);

        return () => clearInterval(timer);
    }, [runningJobIds]);

    useEffect(() => {
        fetchRawRows();
    }, [rawType, rawOffset]);

    const triggerSync = async (type: "items" | "orders" | "qna" | "categories", extraParams?: Record<string, any>) => {
        if (!canTrigger) {
            alert("오너클랜 대표 계정이 설정되어 있지 않습니다. 설정 메뉴에서 먼저 계정을 등록해 주세요.");
            return;
        }

        const confirmMap: Record<string, string> = {
            items: "오너클랜 상품(items) 수집을 시작하시겠습니까?",
            orders: "오너클랜 주문(orders) 수집을 시작하시겠습니까?",
            qna: "오너클랜 QnA 수집을 시작하시겠습니까?",
            categories: "오너클랜 카테고리 수집을 시작하시겠습니까?",
        };

        if (!confirm(confirmMap[type])) return;

        setTriggerLoading(type);
        try {
            const endpoint = `/suppliers/ownerclan/sync/${type}`;
            const res = await api.post<{ jobId: string }>(endpoint, { params: extraParams || {} });
            await fetchJobs();
            alert(`수집 작업이 등록되었습니다. jobId=${res.data.jobId}`);
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setTriggerLoading(null);
        }
    };

    const hasVendorAccount = ownerClanAccounts.some((a) => (a.userType === "vendor" || a.userType === "supplier") && a.isActive);

    return (
        <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <h1 className="text-3xl font-bold tracking-tight">공급사 상품수집</h1>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        disabled={loadingStatus || jobsLoading}
                        onClick={() => {
                            fetchOwnerClanStatus();
                            fetchJobs();
                        }}
                    >
                        새로고침
                    </Button>
                </div>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>오너클랜 계정 상태</CardTitle>
                </CardHeader>
                <CardContent>
                    {loadingStatus && !ownerClanStatus ? (
                        <div className="text-sm text-muted-foreground">불러오는 중...</div>
                    ) : ownerClanStatus?.configured && ownerClanStatus.account ? (
                        <div className="space-y-2">
                            <div className="flex flex-wrap items-center gap-2">
                                <Badge variant="success">설정됨</Badge>
                                {ownerClanStatus.account.isActive ? <Badge variant="secondary">활성</Badge> : <Badge variant="outline">비활성</Badge>}
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div className="text-sm">
                                    <div className="text-muted-foreground">아이디</div>
                                    <div className="font-medium">{ownerClanStatus.account.username}</div>
                                </div>
                                <div className="text-sm">
                                    <div className="text-muted-foreground">토큰 만료</div>
                                    <div className="font-medium">{formatDateTime(ownerClanStatus.account.tokenExpiresAt)}</div>
                                </div>
                                <div className="text-sm">
                                    <div className="text-muted-foreground">업데이트</div>
                                    <div className="font-medium">{formatDateTime(ownerClanStatus.account.updatedAt)}</div>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            <Badge variant="warning">미설정</Badge>
                            <div className="text-sm text-muted-foreground">설정 → 오너클랜 대표 계정을 먼저 등록해 주세요.</div>
                        </div>
                    )}
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>수집 실행</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex flex-wrap gap-2 items-center">
                        <div className="flex items-center gap-2">
                            <div className="text-sm text-muted-foreground">기간</div>
                            <select
                                className="h-10 rounded-md border bg-background px-3 text-sm"
                                value={itemDatePreset}
                                onChange={(e) => setItemDatePreset(e.target.value as any)}
                                disabled={!canTrigger || triggerLoading === "items"}
                            >
                                <option value="1d">최근 1일</option>
                                <option value="3d">최근 3일</option>
                                <option value="7d">최근 7일</option>
                                <option value="30d">최근 30일</option>
                                <option value="all">전체(최근 179일)</option>
                            </select>
                        </div>

                        <Button
                            disabled={!canTrigger}
                            isLoading={triggerLoading === "items"}
                            onClick={() => triggerSync("items", { datePreset: itemDatePreset })}
                        >
                            상품(items)
                        </Button>
                        <Button disabled={!canTrigger} isLoading={triggerLoading === "orders"} onClick={() => triggerSync("orders")}>
                            주문(orders)
                        </Button>
                        <Button disabled={!canTrigger} isLoading={triggerLoading === "qna"} onClick={() => triggerSync("qna")}>
                            QnA(seller)
                        </Button>
                        {hasVendorAccount ? (
                            <Button
                                disabled={!canTrigger}
                                isLoading={triggerLoading === "qna"}
                                variant="outline"
                                onClick={() => triggerSync("qna", { userType: "vendor" })}
                            >
                                QnA(vendor)
                            </Button>
                        ) : (
                            <Button
                                disabled
                                variant="outline"
                                onClick={() => { }}
                                title="seller 계정만으로는 vendor QnA를 수집할 수 없습니다. (필요 시 설정에서 vendor 계정 추가)"
                            >
                                QnA(vendor)
                            </Button>
                        )}
                        <Button disabled={!canTrigger} isLoading={triggerLoading === "categories"} onClick={() => triggerSync("categories")}>
                            카테고리
                        </Button>
                    </div>
                    <div className="mt-2 text-xs text-muted-foreground">
                        셀러 계정 기준으로는 QnA가 0건일 수 있습니다. vendor QnA는 vendor/supplier 계정이 있을 때만 수집 가능합니다.
                    </div>
                    <div className="mt-3 text-sm text-muted-foreground">
                        실행 중인 작업이 있으면 목록이 자동으로 갱신됩니다.
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>수집 Job 모니터링</CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <table className="w-full caption-bottom text-sm text-left">
                            <thead className="[&_tr]:border-b">
                                <tr className="border-b">
                                    <th className="h-12 px-4 align-middle font-medium text-muted-foreground">작업</th>
                                    <th className="h-12 px-4 align-middle font-medium text-muted-foreground">상태</th>
                                    <th className="h-12 px-4 align-middle font-medium text-muted-foreground">진행</th>
                                    <th className="h-12 px-4 align-middle font-medium text-muted-foreground">생성</th>
                                    <th className="h-12 px-4 align-middle font-medium text-muted-foreground">시작</th>
                                    <th className="h-12 px-4 align-middle font-medium text-muted-foreground">종료</th>
                                    <th className="h-12 px-4 align-middle font-medium text-muted-foreground">에러</th>
                                </tr>
                            </thead>
                            <tbody className="[&_tr:last-child]:border-0">
                                {jobsLoading && jobs.length === 0 ? (
                                    <tr>
                                        <td colSpan={7} className="h-24 text-center text-muted-foreground">
                                            불러오는 중...
                                        </td>
                                    </tr>
                                ) : jobs.length === 0 ? (
                                    <tr>
                                        <td colSpan={7} className="h-24 text-center text-muted-foreground">
                                            아직 수집 Job이 없습니다.
                                        </td>
                                    </tr>
                                ) : (
                                    jobs.map((job) => (
                                        <tr key={job.id} className="border-b transition-colors hover:bg-muted/50">
                                            <td className="p-4 align-middle">
                                                <div className="font-medium">{getJobLabel(job.jobType)}</div>
                                                <div className="text-xs text-muted-foreground">{job.id}</div>
                                            </td>
                                            <td className="p-4 align-middle">{getStatusBadge(job.status)}</td>
                                            <td className="p-4 align-middle">{job.progress}</td>
                                            <td className="p-4 align-middle">{formatDateTime(job.createdAt)}</td>
                                            <td className="p-4 align-middle">{formatDateTime(job.startedAt)}</td>
                                            <td className="p-4 align-middle">{formatDateTime(job.finishedAt)}</td>
                                            <td className="p-4 align-middle">
                                                {job.lastError ? (
                                                    <div className="max-w-[520px] whitespace-pre-wrap break-words text-xs text-destructive">
                                                        {job.lastError}
                                                    </div>
                                                ) : job.status === "succeeded" && job.progress === 0 ? (
                                                    <span className="text-muted-foreground text-xs">데이터 없음</span>
                                                ) : (
                                                    <span className="text-muted-foreground">-</span>
                                                )}
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>수집 데이터 조회(Raw)</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex flex-col gap-3">
                        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                            <div className="flex flex-wrap gap-2">
                                <Button variant={rawType === "items" ? "primary" : "outline"} onClick={() => changeRawType("items")}>
                                    상품
                                </Button>
                                <Button variant={rawType === "orders" ? "primary" : "outline"} onClick={() => changeRawType("orders")}>
                                    주문
                                </Button>
                                <Button variant={rawType === "qna" ? "primary" : "outline"} onClick={() => changeRawType("qna")}>
                                    QnA
                                </Button>
                                <Button
                                    variant={rawType === "categories" ? "primary" : "outline"}
                                    onClick={() => changeRawType("categories")}
                                >
                                    카테고리
                                </Button>
                            </div>

                            <div className="flex flex-col sm:flex-row gap-2">
                                <Input
                                    placeholder={`${getRawLabel(rawType)} 검색`}
                                    value={rawQuery}
                                    onChange={(e) => setRawQuery(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter") {
                                            setRawSelectedId(null);
                                            setRawDetail(null);

                                            if (rawOffset === 0) {
                                                fetchRawRows(0);
                                            } else {
                                                setRawOffset(0);
                                            }
                                        }
                                    }}
                                />
                                <div className="flex gap-2">
                                    <Button
                                        variant="outline"
                                        disabled={rawLoading}
                                        onClick={() => {
                                            setRawSelectedId(null);
                                            setRawDetail(null);

                                            if (rawOffset === 0) {
                                                fetchRawRows(0);
                                            } else {
                                                setRawOffset(0);
                                            }
                                        }}
                                    >
                                        검색
                                    </Button>
                                    <Button variant="outline" disabled={rawLoading} onClick={() => fetchRawRows()}>
                                        새로고침
                                    </Button>
                                </div>
                            </div>
                        </div>

                        <div className="flex items-center gap-2">
                            <Button
                                variant="outline"
                                disabled={rawLoading || rawOffset === 0}
                                onClick={() => setRawOffset((prev) => Math.max(0, prev - rawLimit))}
                            >
                                이전
                            </Button>
                            <Button
                                variant="outline"
                                disabled={rawLoading || rawRows.length < rawLimit}
                                onClick={() => setRawOffset((prev) => prev + rawLimit)}
                            >
                                다음
                            </Button>
                            <div className="text-sm text-muted-foreground">offset: {rawOffset}</div>
                        </div>

                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                            <div className="overflow-x-auto rounded-md border">
                                <table className="w-full caption-bottom text-sm text-left">
                                    <thead className="[&_tr]:border-b">
                                        {rawType === "items" ? (
                                            <tr className="border-b">
                                                <th className="h-12 px-4 align-middle font-medium text-muted-foreground">itemCode</th>
                                                <th className="h-12 px-4 align-middle font-medium text-muted-foreground">itemKey</th>
                                                <th className="h-12 px-4 align-middle font-medium text-muted-foreground">fetched</th>
                                            </tr>
                                        ) : rawType === "orders" ? (
                                            <tr className="border-b">
                                                <th className="h-12 px-4 align-middle font-medium text-muted-foreground">orderId</th>
                                                <th className="h-12 px-4 align-middle font-medium text-muted-foreground">accountId</th>
                                                <th className="h-12 px-4 align-middle font-medium text-muted-foreground">fetched</th>
                                            </tr>
                                        ) : rawType === "qna" ? (
                                            <tr className="border-b">
                                                <th className="h-12 px-4 align-middle font-medium text-muted-foreground">qnaId</th>
                                                <th className="h-12 px-4 align-middle font-medium text-muted-foreground">accountId</th>
                                                <th className="h-12 px-4 align-middle font-medium text-muted-foreground">fetched</th>
                                            </tr>
                                        ) : (
                                            <tr className="border-b">
                                                <th className="h-12 px-4 align-middle font-medium text-muted-foreground">categoryId</th>
                                                <th className="h-12 px-4 align-middle font-medium text-muted-foreground">fetched</th>
                                            </tr>
                                        )}
                                    </thead>
                                    <tbody className="[&_tr:last-child]:border-0">
                                        {rawLoading && rawRows.length === 0 ? (
                                            <tr>
                                                <td colSpan={3} className="h-24 text-center text-muted-foreground">
                                                    불러오는 중...
                                                </td>
                                            </tr>
                                        ) : rawRows.length === 0 ? (
                                            <tr>
                                                <td colSpan={3} className="h-24 text-center text-muted-foreground">
                                                    데이터가 없습니다.
                                                </td>
                                            </tr>
                                        ) : rawType === "items" ? (
                                            (rawRows as OwnerClanItemRawRow[]).map((row) => (
                                                <tr
                                                    key={row.id}
                                                    className="border-b transition-colors hover:bg-muted/50 cursor-pointer"
                                                    onClick={() => {
                                                        setRawSelectedId(row.id);
                                                        fetchRawDetail(row.id);
                                                    }}
                                                >
                                                    <td className="p-4 align-middle">
                                                        <div className="font-medium">{row.itemCode ?? "-"}</div>
                                                        <div className="text-xs text-muted-foreground">{row.id}</div>
                                                    </td>
                                                    <td className="p-4 align-middle">{row.itemKey ?? "-"}</td>
                                                    <td className="p-4 align-middle">{formatDateTime(row.fetchedAt)}</td>
                                                </tr>
                                            ))
                                        ) : rawType === "orders" ? (
                                            (rawRows as OwnerClanOrderRawRow[]).map((row) => (
                                                <tr
                                                    key={row.id}
                                                    className="border-b transition-colors hover:bg-muted/50 cursor-pointer"
                                                    onClick={() => {
                                                        setRawSelectedId(row.id);
                                                        fetchRawDetail(row.id);
                                                    }}
                                                >
                                                    <td className="p-4 align-middle">
                                                        <div className="font-medium">{row.orderId}</div>
                                                        <div className="text-xs text-muted-foreground">{row.id}</div>
                                                    </td>
                                                    <td className="p-4 align-middle">
                                                        <div className="text-xs break-all">{row.accountId}</div>
                                                    </td>
                                                    <td className="p-4 align-middle">{formatDateTime(row.fetchedAt)}</td>
                                                </tr>
                                            ))
                                        ) : rawType === "qna" ? (
                                            (rawRows as OwnerClanQnaRawRow[]).map((row) => (
                                                <tr
                                                    key={row.id}
                                                    className="border-b transition-colors hover:bg-muted/50 cursor-pointer"
                                                    onClick={() => {
                                                        setRawSelectedId(row.id);
                                                        fetchRawDetail(row.id);
                                                    }}
                                                >
                                                    <td className="p-4 align-middle">
                                                        <div className="font-medium">{row.qnaId}</div>
                                                        <div className="text-xs text-muted-foreground">{row.id}</div>
                                                    </td>
                                                    <td className="p-4 align-middle">
                                                        <div className="text-xs break-all">{row.accountId}</div>
                                                    </td>
                                                    <td className="p-4 align-middle">{formatDateTime(row.fetchedAt)}</td>
                                                </tr>
                                            ))
                                        ) : (
                                            (rawRows as OwnerClanCategoryRawRow[]).map((row) => (
                                                <tr
                                                    key={row.id}
                                                    className="border-b transition-colors hover:bg-muted/50 cursor-pointer"
                                                    onClick={() => {
                                                        setRawSelectedId(row.id);
                                                        fetchRawDetail(row.id);
                                                    }}
                                                >
                                                    <td className="p-4 align-middle">
                                                        <div className="font-medium">{row.categoryId}</div>
                                                        <div className="text-xs text-muted-foreground">{row.id}</div>
                                                    </td>
                                                    <td className="p-4 align-middle">{formatDateTime(row.fetchedAt)}</td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>

                            <div className="rounded-md border p-4">
                                <div className="flex items-center justify-between gap-2">
                                    <div className="font-medium">상세 JSON</div>
                                    {rawSelectedId ? <div className="text-xs text-muted-foreground">{rawSelectedId}</div> : null}
                                </div>

                                {rawDetailLoading ? (
                                    <div className="mt-3 text-sm text-muted-foreground">불러오는 중...</div>
                                ) : rawDetail ? (
                                    <pre className="mt-3 max-h-[560px] overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-xs">
                                        {JSON.stringify(rawDetail, null, 2)}
                                    </pre>
                                ) : (
                                    <div className="mt-3 text-sm text-muted-foreground">왼쪽 목록에서 항목을 선택해 주세요.</div>
                                )}
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
