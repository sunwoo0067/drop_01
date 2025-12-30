import { useRef, useEffect } from "react";
import { Search, Download, X, Activity, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";

type LogFilter = {
    step: string;
    status: string;
    search: string;
};

interface LogViewerProps {
    events: any[];
    filteredEvents: any[];
    logFilter: LogFilter;
    setLogFilter: (filter: LogFilter) => void;
    autoScroll: boolean;
    setAutoScroll: (value: boolean) => void;
    lastUpdatedAt: Date | null;
}

export function LogViewer({
    events,
    filteredEvents,
    logFilter,
    setLogFilter,
    autoScroll,
    setAutoScroll,
    lastUpdatedAt
}: LogViewerProps) {
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (autoScroll && scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [filteredEvents, autoScroll]);

    const exportLogs = () => {
        const dataStr = JSON.stringify(filteredEvents, null, 2);
        const dataUri = 'data:application/json;charset=utf-8,' + encodeURIComponent(dataStr);
        const exportName = 'orchestration_logs.json';
        const linkElement = document.createElement('a');
        linkElement.setAttribute('href', dataUri);
        linkElement.setAttribute('download', exportName);
        linkElement.click();
    };

    const getStepColor = (step: string) => {
        if (step === "FAIL") return "text-destructive";
        if (step === "START") return "text-info";
        if (step === "SUCCESS") return "text-success";
        return "text-warning";
    };

    return (
        <Card className="border border-border">
            <CardHeader className="border-b border-border py-2">
                <CardTitle className="text-xs flex items-center gap-2">
                    <div className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary/75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
                    </div>
                    Live AI Orchestration Logs
                </CardTitle>
            </CardHeader>
            {/* 로그 필터 및 검색 */}
            <div className="border-b border-border p-2 flex flex-wrap gap-2 items-center">
                <div className="flex items-center gap-1.5 flex-1 min-w-[180px]">
                    <Search className="h-3 w-3 text-muted-foreground" />
                    <Input
                        placeholder="로그 검색..."
                        value={logFilter.search}
                        onChange={(e) => setLogFilter({ ...logFilter, search: e.target.value })}
                        className="bg-muted border-border text-[10px] h-6"
                        size="sm"
                    />
                </div>
                <Select
                    value={logFilter.step}
                    onChange={(e) => setLogFilter({ ...logFilter, step: e.target.value })}
                    options={[
                        { value: "ALL", label: "모든 단계" },
                        { value: "PLANNING", label: "PLANNING" },
                        { value: "OPTIMIZATION", label: "OPTIMIZATION" },
                        { value: "SOURCING", label: "SOURCING" },
                        { value: "LISTING", label: "LISTING" },
                        { value: "PREMIUM", label: "PREMIUM" }
                    ]}
                    className="w-[120px]"
                />
                <Select
                    value={logFilter.status}
                    onChange={(e) => setLogFilter({ ...logFilter, status: e.target.value })}
                    options={[
                        { value: "ALL", label: "모든 상태" },
                        { value: "START", label: "START" },
                        { value: "IN_PROGRESS", label: "IN_PROGRESS" },
                        { value: "SUCCESS", label: "SUCCESS" },
                        { value: "FAIL", label: "FAIL" }
                    ]}
                    className="w-[100px]"
                />
                <Button
                    variant="outline"
                    size="xs"
                    onClick={() => setAutoScroll(!autoScroll)}
                    className={autoScroll ? "bg-primary/10" : ""}
                >
                    <Activity className="h-3 w-3 mr-1" />
                    {autoScroll ? "스크롤 ON" : "스크롤 OFF"}
                </Button>
                <Button
                    variant="outline"
                    size="xs"
                    onClick={exportLogs}
                >
                    <Download className="h-3 w-3 mr-1" />
                    내보내기
                </Button>
                {(logFilter.step !== "ALL" || logFilter.status !== "ALL" || logFilter.search) && (
                    <Button
                        variant="outline"
                        size="xs"
                        onClick={() => setLogFilter({ step: "ALL", status: "ALL", search: "" })}
                    >
                        <X className="h-3 w-3 mr-1" />
                        필터 초기화
                    </Button>
                )}
            </div>
            <CardContent className="p-0">
                <div ref={scrollRef} className="h-[300px] overflow-y-auto p-2 font-mono text-[10px] leading-relaxed table-scroll">
                    {filteredEvents.length > 0 ? (
                        filteredEvents.slice().reverse().map((event, i) => (
                            <div key={event.id || i} className="flex gap-2 hover:bg-muted/50 transition-colors py-0.5 px-1 rounded border-l border-transparent">
                                <span className="text-muted-foreground shrink-0 font-mono">
                                    [{new Date(event.created_at).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}]
                                </span>
                                <span className={`shrink-0 font-bold w-12 ${getStepColor(event.status)}`}>
                                    {event.status}
                                </span>
                                <span className="text-muted-foreground/50 shrink-0">|</span>
                                <span className="text-muted-foreground shrink-0 w-16 font-mono uppercase text-[9px] mt-0.5">
                                    {event.step}
                                </span>
                                <span className="text-foreground break-all flex-1">
                                    {event.message}
                                </span>
                            </div>
                        ))
                    ) : (
                        <div className="flex flex-col items-center justify-center h-full text-muted-foreground italic">
                            <RefreshCw className="h-6 w-6 mb-3 animate-spin opacity-20" />
                            <p>연결 대기 중... 로그를 기다리고 있습니다.</p>
                        </div>
                    )}
                    <div id="log-bottom" />
                </div>
            </CardContent>
        </Card>
    );
}
