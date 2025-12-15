"use client";

import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import api from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";

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

    const [jobs, setJobs] = useState<SupplierSyncJob[]>([]);
    const [jobsLoading, setJobsLoading] = useState(false);

    const [triggerLoading, setTriggerLoading] = useState<string | null>(null);

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

    useEffect(() => {
        fetchOwnerClanStatus();
        fetchJobs();
    }, []);

    useEffect(() => {
        if (runningJobIds.size === 0) return;

        const timer = setInterval(() => {
            fetchJobs();
        }, 2500);

        return () => clearInterval(timer);
    }, [runningJobIds]);

    const triggerSync = async (type: "items" | "orders" | "qna" | "categories") => {
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
            const res = await api.post<{ jobId: string }>(endpoint, { params: {} });
            await fetchJobs();
            alert(`수집 작업이 등록되었습니다. jobId=${res.data.jobId}`);
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setTriggerLoading(null);
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <h1 className="text-3xl font-bold tracking-tight">공급사 수집</h1>
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
                    <div className="flex flex-wrap gap-2">
                        <Button disabled={!canTrigger} isLoading={triggerLoading === "items"} onClick={() => triggerSync("items")}>
                            상품(items)
                        </Button>
                        <Button disabled={!canTrigger} isLoading={triggerLoading === "orders"} onClick={() => triggerSync("orders")}>
                            주문(orders)
                        </Button>
                        <Button disabled={!canTrigger} isLoading={triggerLoading === "qna"} onClick={() => triggerSync("qna")}>
                            QnA
                        </Button>
                        <Button disabled={!canTrigger} isLoading={triggerLoading === "categories"} onClick={() => triggerSync("categories")}>
                            카테고리
                        </Button>
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
        </div>
    );
}
