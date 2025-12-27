"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Activity, Server, ShieldCheck, AlertCircle, RefreshCw } from "lucide-react";

interface AccountHealth {
    account_id: string;
    account_name: string;
    market_code: string;
    status: "healthy" | "unhealthy" | "error" | "unknown";
    message: string;
}

interface SystemHealth {
    status: string;
    database: string;
    timestamp: string | null;
}

export function HealthStatus() {
    const [system, setSystem] = useState<SystemHealth | null>(null);
    const [accounts, setAccounts] = useState<AccountHealth[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    const fetchHealth = async () => {
        setIsLoading(true);
        try {
            const [sysRes, accRes] = await Promise.all([
                api.get("/health/system"),
                api.get("/health/accounts"),
            ]);
            setSystem(sysRes.data);
            setAccounts(accRes.data);
        } catch (e) {
            console.error("Failed to fetch health status", e);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchHealth();
        const interval = setInterval(fetchHealth, 30000); // 30초마다 갱신
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            <Card className="border-primary/20 bg-accent/5">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                    <CardTitle className="text-sm font-bold flex items-center gap-2">
                        <Server className="h-4 w-4 text-primary" />
                        시스템 상태
                    </CardTitle>
                    <button onClick={fetchHealth} disabled={isLoading} className="text-muted-foreground hover:text-primary transition-colors">
                        <RefreshCw className={`h-3 w-3 ${isLoading ? "animate-spin" : ""}`} />
                    </button>
                </CardHeader>
                <CardContent>
                    <div className="space-y-3">
                        <div className="flex items-center justify-between">
                            <span className="text-xs text-muted-foreground">서버 상태</span>
                            <Badge variant={system?.status === "healthy" ? "success" : "destructive"}>
                                {system?.status === "healthy" ? "정상" : "오류"}
                            </Badge>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="text-xs text-muted-foreground">데이터베이스</span>
                            <Badge variant={system?.database === "ok" ? "success" : "destructive"}>
                                {system?.database === "ok" ? "연결됨" : "오류"}
                            </Badge>
                        </div>
                        {system?.timestamp && (
                            <div className="text-[10px] text-muted-foreground text-right italic">
                                Last checked: {new Date(system.timestamp).toLocaleTimeString()}
                            </div>
                        )}
                    </div>
                </CardContent>
            </Card>

            <Card className="col-span-1 md:col-span-2 border-primary/20 bg-accent/5">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-bold flex items-center gap-2">
                        <ShieldCheck className="h-4 w-4 text-emerald-500" />
                        마켓 계정 API 상태
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid gap-3 sm:grid-cols-2">
                        {accounts.map((acc) => (
                            <div key={acc.account_id} className="flex items-center justify-between p-3 rounded-xl bg-background/50 border border-border/50">
                                <div className="flex flex-col gap-0.5">
                                    <span className="text-xs font-bold truncate max-w-[150px]">{acc.account_name}</span>
                                    <span className="text-[10px] text-muted-foreground uppercase">{acc.market_code}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    {acc.status === "healthy" ? (
                                        <Badge variant="success" className="h-5">정상</Badge>
                                    ) : (
                                        <div className="group relative">
                                            <Badge variant="destructive" className="h-5 flex items-center gap-1 cursor-help">
                                                <AlertCircle className="h-3 w-3" />
                                                오류
                                            </Badge>
                                            {acc.message && (
                                                <div className="absolute bottom-full right-0 mb-2 w-48 p-2 bg-popover text-popover-foreground text-[10px] rounded-lg shadow-xl opacity-0 group-hover:opacity-100 transition-opacity z-50 pointer-events-none border border-border">
                                                    {acc.message}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                        {accounts.length === 0 && !isLoading && (
                            <div className="col-span-full py-4 text-center text-xs text-muted-foreground italic">
                                활성화된 마켓 계정이 없습니다.
                            </div>
                        )}
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
