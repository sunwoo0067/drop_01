import { Bell, Settings, Zap } from "lucide-react";
import { Button } from "@/components/ui/Button";

interface DashboardToolbarProps {
    isLoading: boolean;
    isRunning: boolean;
    onRunCycle: () => void;
    onToggleSettings: () => void;
    onToggleNotifications: () => void;
    notificationCount: number;
}

export function DashboardToolbar({
    isLoading,
    isRunning,
    onRunCycle,
    onToggleSettings,
    onToggleNotifications,
    notificationCount
}: DashboardToolbarProps) {
    return (
        <div className="flex items-center justify-between px-3 py-2 border border-border bg-card rounded-sm">
            <div className="flex items-center gap-3">
                <h1 className="text-sm font-semibold text-foreground">대시보드</h1>
                <span className="text-[10px] text-muted-foreground">
                    자동화 시스템의 실시간 가동 현황 및 핵심 지표
                </span>
            </div>

            <div className="flex items-center gap-2">
                <Button variant="outline" size="xs" onClick={onToggleSettings}>
                    <Settings className="h-3 w-3 mr-1.5" />
                    설정
                </Button>
                <Button
                    variant="outline"
                    size="xs"
                    onClick={onToggleNotifications}
                    className="relative"
                >
                    <Bell className="h-3 w-3 mr-1.5" />
                    알림
                    {notificationCount > 0 && (
                        <span className="ml-1.5 rounded-sm bg-destructive px-1 py-0.5 text-[9px] font-bold text-destructive-foreground">
                            {notificationCount}
                        </span>
                    )}
                </Button>
                <Button
                    size="xs"
                    onClick={onRunCycle}
                    disabled={isLoading || isRunning}
                >
                    <Zap className="h-3 w-3 mr-1.5" />
                    수동 실행
                </Button>
            </div>
        </div>
    );
}
