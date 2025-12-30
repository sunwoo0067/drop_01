import { Bot, Play, Pause, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";

interface OrchestrationControlProps {
    isRunning: boolean;
    isLoading: boolean;
    orchestrationProgress: {
        currentStep: string;
        progress: number;
        totalSteps: number;
    };
    onRunCycle: (dryRun: boolean) => void;
}

export function OrchestrationControl({
    isRunning,
    isLoading,
    orchestrationProgress,
    onRunCycle
}: OrchestrationControlProps) {
    return (
        <Card className="border border-border">
            <CardHeader className="py-2">
                <CardTitle className="flex items-center gap-2 text-xs">
                    <Bot className="h-3.5 w-3.5 text-primary" />
                    AI 오케스트레이션 제어 센터
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
                {/* 진행률 표시 */}
                {isRunning && (
                    <div className="space-y-2">
                        <div className="flex items-center justify-between text-[11px]">
                            <span className="font-medium">{orchestrationProgress.currentStep}</span>
                            <span className="text-muted-foreground">{Math.round(orchestrationProgress.progress)}%</span>
                        </div>
                        <div className="h-1.5 bg-muted rounded-sm overflow-hidden">
                            <div
                                className="h-full bg-primary transition-all"
                                style={{ width: `${orchestrationProgress.progress}%` }}
                            />
                        </div>
                    </div>
                )}
                <div className="flex flex-col gap-2">
                    <p className="text-[10px] text-muted-foreground">
                        AI가 자동으로 시장 트렌드를 분석하고, 상품을 소싱하여 1단계 가공(상품명 최적화) 후 등록된 모든 마켓에 전송합니다.
                    </p>
                    <div className="flex items-center gap-2">
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider ${
                            isRunning ? 'bg-success/10 text-success' : 'bg-muted text-muted-foreground'
                        }`}>
                            {isRunning ? 'System Running' : 'System Ready'}
                        </span>
                        <span className="text-[10px] text-muted-foreground italic">
                            대기 중인 최적화 사이클: 즉시 실행 가능
                        </span>
                    </div>
                </div>
                <div className="flex items-center gap-2 pt-2 border-t border-border/50">
                    <Button
                        onClick={() => onRunCycle(true)}
                        disabled={isLoading || isRunning}
                        variant="outline"
                        size="xs"
                        className="flex-1"
                    >
                        <RefreshCw className={`h-3 w-3 mr-1 ${isLoading ? 'animate-spin' : ''}`} />
                        테스트 가동 (Dry Run)
                    </Button>
                    <Button
                        onClick={() => onRunCycle(false)}
                        disabled={isLoading || isRunning}
                        size="xs"
                        className="flex-1"
                    >
                        {isRunning ? (
                            <>
                                <Pause className="mr-1 h-3 w-3" />
                                가동 중...
                            </>
                        ) : (
                            <>
                                <Play className="mr-1 h-3 w-3" />
                                자동 운영 시작
                            </>
                        )}
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}
