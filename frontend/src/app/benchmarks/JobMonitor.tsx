'use client';

import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Loader2, RefreshCw, AlertTriangle, CheckCircle2, RotateCcw } from "lucide-react";

export default function JobMonitor() {
    const [jobs, setJobs] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [isRefreshing, setIsRefreshing] = useState(false);

    const fetchJobs = async (silent = false) => {
        if (!silent) setIsLoading(true);
        try {
            const resp = await api.get('/benchmarks/jobs', { params: { limit: 20 } });
            setJobs(resp.data.items || []);
        } catch (err) {
            console.error(err);
        } finally {
            setIsLoading(false);
        }
    };

    const handleRetry = async (id: string) => {
        try {
            await api.post(`/benchmarks/jobs/${id}/retry`);
            fetchJobs(true);
        } catch (err) {
            alert("재시도 요청 실패");
        }
    };

    useEffect(() => {
        fetchJobs();
        const interval = setInterval(() => fetchJobs(true), 3000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">수집 작업 히스토리</h3>
                <Button variant="ghost" size="sm" onClick={() => fetchJobs()} disabled={isLoading}>
                    <RefreshCw className={`h-3 w-3 mr-1 ${isLoading ? 'animate-spin' : ''}`} />
                    새로고침
                </Button>
            </div>

            <div className="space-y-3">
                {jobs.length === 0 && !isLoading && (
                    <div className="text-center py-10 bg-muted/20 rounded-lg border border-dashed text-muted-foreground text-sm">
                        최근 수행된 작업이 없습니다.
                    </div>
                )}

                {jobs.map((job) => (
                    <div key={job.id} className="p-3 border rounded-lg bg-background shadow-sm space-y-3">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <Badge variant={job.status === 'succeeded' ? 'outline' : job.status === 'failed' ? 'destructive' : 'default'} className="text-[10px]">
                                    {job.marketCode}
                                </Badge>
                                <span className="text-xs font-medium truncate max-w-[150px]">{job.categoryUrl || '기본 랭킹'}</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-[10px] text-muted-foreground">{new Date(job.createdAt).toLocaleTimeString()}</span>
                                {job.status === 'failed' && (
                                    <Button size="sm" variant="outline" className="h-6 px-2 text-[10px]" onClick={() => handleRetry(job.id)}>
                                        <RotateCcw className="h-2.5 w-2.5 mr-1" />
                                        재시도
                                    </Button>
                                )}
                            </div>
                        </div>

                        <div className="space-y-1.5">
                            <div className="flex justify-between text-[10px]">
                                <span className="flex items-center gap-1 font-semibold">
                                    {job.status === 'running' && <Loader2 className="h-2.5 w-2.5 animate-spin text-primary" />}
                                    {job.status === 'succeeded' && <CheckCircle2 className="h-2.5 w-2.5 text-green-500" />}
                                    {job.status === 'failed' && <AlertTriangle className="h-2.5 w-2.5 text-destructive" />}
                                    {job.status.toUpperCase()}
                                </span>
                                <span className="text-muted-foreground">
                                    {job.processedCount} / {job.totalCount} 수집 ({job.progress}%)
                                </span>
                            </div>
                            <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                                <div
                                    className={`h-full transition-all duration-500 rounded-full ${job.status === 'failed' ? 'bg-destructive' :
                                        job.status === 'succeeded' ? 'bg-green-500' : 'bg-primary'
                                        }`}
                                    style={{ width: `${job.progress}%` }}
                                />
                            </div>
                        </div>

                        {job.lastError && (
                            <p className="text-[9px] text-destructive truncate bg-red-50 p-1 rounded border border-red-100 italic" title={job.lastError}>
                                Error: {job.lastError}
                            </p>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
