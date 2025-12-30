"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Bot, Activity, Zap, RefreshCw, Clock, CheckCircle, AlertTriangle, Settings, Play, Pause, TrendingUp, Target, Database, Cpu, Network } from "lucide-react";
import { motion } from "framer-motion";

const container = {
    hidden: { opacity: 0 },
    show: {
        opacity: 1,
        transition: {
            staggerChildren: 0.1
        }
    }
};

const item = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 }
};

type AgentStatus = {
    sourcing: {
        status: string;
        message: string;
        queue_size: number;
    };
    processing: {
        status: string;
        message: string;
        queue_size: number;
    };
    analysis?: {
        status: string;
        message: string;
        active_tasks: number;
    };
};

export default function AgentsPage() {
    const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [isRunning, setIsRunning] = useState(false);

    const fetchAgentStatus = async () => {
        try {
            const res = await api.get("/orchestration/agents/status");
            setAgentStatus(res.data);
        } catch (e) {
            console.error("Failed to fetch agent status", e);
        }
    };

    const handleRefresh = async () => {
        setIsLoading(true);
        await fetchAgentStatus();
        setIsLoading(false);
    };

    const handleToggleAgent = async (agentType: string) => {
        // 에이전트 시작/중지 로직 (백엔드 API 필요)
        void agentType;
        setIsRunning(!isRunning);
    };

    useEffect(() => {
        const timeout = setTimeout(() => {
            void fetchAgentStatus();
        }, 0);
        const interval = setInterval(fetchAgentStatus, 5000);
        return () => {
            clearTimeout(timeout);
            clearInterval(interval);
        };
    }, []);

    const getStatusColor = (status: string) => {
        switch (status?.toLowerCase()) {
            case "healthy":
            case "live":
            case "running":
                return "emerald";
            case "idle":
                return "amber";
            case "error":
            case "stopped":
                return "red";
            default:
                return "gray";
        }
    };

    const getStatusIcon = (status: string) => {
        switch (status?.toLowerCase()) {
            case "healthy":
            case "live":
            case "running":
                return <Activity className="h-4 w-4" />;
            case "idle":
                return <Clock className="h-4 w-4" />;
            case "error":
            case "stopped":
                return <AlertTriangle className="h-4 w-4" />;
            default:
                return <Activity className="h-4 w-4" />;
        }
    };

    return (
        <motion.div
            variants={container}
            initial="hidden"
            animate="show"
            className="space-y-4 py-4"
        >
            {/* Header */}
            <motion.div variants={item} className="flex items-center justify-between px-3 py-2 border border-border bg-card rounded-sm">
                <div className="flex items-center gap-3">
                    <div className="h-6 w-6 rounded-sm bg-primary/10 flex items-center justify-center">
                        <Bot className="h-3 w-3 text-primary" />
                    </div>
                    <div>
                        <h1 className="text-sm font-semibold text-foreground">AI 에이전트 관리</h1>
                        <p className="text-[10px] text-muted-foreground">
                            에이전트 상태 모니터링 및 제어
                        </p>
                    </div>
                </div>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={handleRefresh}
                    disabled={isLoading}
                >
                    <RefreshCw className={`h-3 w-3 mr-1.5 ${isLoading ? 'animate-spin' : ''}`} />
                    새로고침
                </Button>
            </motion.div>

            {/* 시스템 개요 */}
            <motion.div variants={item}>
                <Card className="border border-border">
                    <CardHeader className="py-2">
                        <CardTitle className="flex items-center gap-2 text-xs">
                            <Zap className="h-3.5 w-3.5 text-primary" />
                            시스템 개요
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="py-2">
                        <div className="grid gap-3 md:grid-cols-4">
                            <div className="flex items-center gap-3">
                                <div className="h-7 w-7 rounded-sm bg-muted flex items-center justify-center">
                                    <Bot className="h-3.5 w-3.5 text-primary" />
                                </div>
                                <div>
                                    <div className="text-lg font-semibold">3</div>
                                    <div className="text-[10px] font-medium text-muted-foreground">활성 에이전트</div>
                                </div>
                            </div>
                            <div className="flex items-center gap-3">
                                <div className="h-7 w-7 rounded-sm bg-muted flex items-center justify-center">
                                    <Activity className="h-3.5 w-3.5 text-emerald-500" />
                                </div>
                                <div>
                                    <div className="text-lg font-semibold text-emerald-600">
                                        {((agentStatus?.sourcing?.queue_size || 0) + (agentStatus?.processing?.queue_size || 0))}
                                    </div>
                                    <div className="text-[10px] font-medium text-muted-foreground">대기 작업</div>
                                </div>
                            </div>
                            <div className="flex items-center gap-3">
                                <div className="h-7 w-7 rounded-sm bg-muted flex items-center justify-center">
                                    <Cpu className="h-3.5 w-3.5 text-blue-500" />
                                </div>
                                <div>
                                    <div className="text-lg font-semibold text-blue-600">100%</div>
                                    <div className="text-[10px] font-medium text-muted-foreground">가용성</div>
                                </div>
                            </div>
                            <div className="flex items-center gap-3">
                                <div className="h-7 w-7 rounded-sm bg-muted flex items-center justify-center">
                                    <Network className="h-3.5 w-3.5 text-amber-500" />
                                </div>
                                <div>
                                    <div className="text-lg font-semibold text-amber-600">Active</div>
                                    <div className="text-[10px] font-medium text-muted-foreground">시스템 상태</div>
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </motion.div>

            {/* 에이전트 카드 */}
            <motion.div variants={container} className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                {/* Sourcing Agent */}
                <motion.div variants={item}>
                    <Card className="h-full border-l-4 border-l-emerald-500">
                        <CardHeader>
                            <CardTitle className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <Target className="h-5 w-5 text-emerald-500" />
                                    Sourcing Agent
                                </div>
                                <div className={`px-2 py-1 rounded-full bg-${getStatusColor(agentStatus?.sourcing?.status || 'gray')}-500/20 text-[10px] font-black uppercase text-${getStatusColor(agentStatus?.sourcing?.status || 'gray')}-600 tracking-tighter flex items-center gap-1`}>
                                    {getStatusIcon(agentStatus?.sourcing?.status || 'idle')}
                                    {agentStatus?.sourcing?.status || 'Idle'}
                                </div>
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <p className="text-sm text-muted-foreground">
                                시장 트렌드를 분석하고 수익성 있는 상품 후보군을 자동으로 소싱합니다.
                            </p>
                            <div className="space-y-2">
                                <div className="flex items-center justify-between text-sm">
                                    <span className="font-medium">대기 큐</span>
                                    <span className="text-lg font-black text-emerald-500">
                                        {agentStatus?.sourcing?.queue_size || 0}
                                    </span>
                                </div>
                                <div className="h-2 bg-muted rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-emerald-500 transition-all"
                                        style={{ width: `${Math.min((agentStatus?.sourcing?.queue_size || 0) * 2, 100)}%` }}
                                    />
                                </div>
                            </div>
                            <div className="text-xs text-muted-foreground">
                                {agentStatus?.sourcing?.message || "새로운 상품 후보군을 탐색하고 있습니다."}
                            </div>
                            <div className="flex gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="flex-1"
                                    onClick={() => handleToggleAgent('sourcing')}
                                >
                                    {isRunning ? <Pause className="h-3 w-3 mr-1" /> : <Play className="h-3 w-3 mr-1" />}
                                    {isRunning ? '중지' : '시작'}
                                </Button>
                                <Button variant="ghost" size="icon">
                                    <Settings className="h-4 w-4" />
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>

                {/* Processing Agent */}
                <motion.div variants={item}>
                    <Card className="h-full border-l-4 border-l-primary">
                        <CardHeader>
                            <CardTitle className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <Cpu className="h-5 w-5 text-primary" />
                                    Processing Agent
                                </div>
                                <div className={`px-2 py-1 rounded-full bg-${getStatusColor(agentStatus?.processing?.status || 'gray')}-500/20 text-[10px] font-black uppercase text-${getStatusColor(agentStatus?.processing?.status || 'gray')}-600 tracking-tighter flex items-center gap-1`}>
                                    {getStatusIcon(agentStatus?.processing?.status || 'idle')}
                                    {agentStatus?.processing?.status || 'Idle'}
                                </div>
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <p className="text-sm text-muted-foreground">
                                상품 데이터 SEO 최적화, 이미지 가공, 상세페이지 생성 등을 자동으로 처리합니다.
                            </p>
                            <div className="space-y-2">
                                <div className="flex items-center justify-between text-sm">
                                    <span className="font-medium">대기 큐</span>
                                    <span className="text-lg font-black text-primary">
                                        {agentStatus?.processing?.queue_size || 0}
                                    </span>
                                </div>
                                <div className="h-2 bg-muted rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-primary transition-all"
                                        style={{ width: `${Math.min((agentStatus?.processing?.queue_size || 0) * 2, 100)}%` }}
                                    />
                                </div>
                            </div>
                            <div className="text-xs text-muted-foreground">
                                {agentStatus?.processing?.message || "데이터 SEO 최적화 및 이미지 가공 엔진 대기 중"}
                            </div>
                            <div className="flex gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="flex-1"
                                    onClick={() => handleToggleAgent('processing')}
                                >
                                    {isRunning ? <Pause className="h-3 w-3 mr-1" /> : <Play className="h-3 w-3 mr-1" />}
                                    {isRunning ? '중지' : '시작'}
                                </Button>
                                <Button variant="ghost" size="icon">
                                    <Settings className="h-4 w-4" />
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>

                {/* Analysis Agent */}
                <motion.div variants={item}>
                    <Card className="h-full border-l-4 border-l-blue-500">
                        <CardHeader>
                            <CardTitle className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <TrendingUp className="h-5 w-5 text-blue-500" />
                                    Analysis Agent
                                </div>
                                <div className={`px-2 py-1 rounded-full bg-${getStatusColor(agentStatus?.analysis?.status || 'gray')}-500/20 text-[10px] font-black uppercase text-${getStatusColor(agentStatus?.analysis?.status || 'gray')}-600 tracking-tighter flex items-center gap-1`}>
                                    {getStatusIcon(agentStatus?.analysis?.status || 'idle')}
                                    {agentStatus?.analysis?.status || 'Idle'}
                                </div>
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <p className="text-sm text-muted-foreground">
                                판매 데이터 분석, 수익성 예측, 시장 트렌드 분석을 수행합니다.
                            </p>
                            <div className="space-y-2">
                                <div className="flex items-center justify-between text-sm">
                                    <span className="font-medium">활성 작업</span>
                                    <span className="text-lg font-black text-blue-500">
                                        {agentStatus?.analysis?.active_tasks || 0}
                                    </span>
                                </div>
                                <div className="h-2 bg-muted rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-blue-500 transition-all"
                                        style={{ width: `${Math.min((agentStatus?.analysis?.active_tasks || 0) * 10, 100)}%` }}
                                    />
                                </div>
                            </div>
                            <div className="text-xs text-muted-foreground">
                                {agentStatus?.analysis?.message || "판매 데이터 분석 및 예측 모델 준비 중"}
                            </div>
                            <div className="flex gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="flex-1"
                                    onClick={() => handleToggleAgent('analysis')}
                                >
                                    {isRunning ? <Pause className="h-3 w-3 mr-1" /> : <Play className="h-3 w-3 mr-1" />}
                                    {isRunning ? '중지' : '시작'}
                                </Button>
                                <Button variant="ghost" size="icon">
                                    <Settings className="h-4 w-4" />
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>
            </motion.div>

            {/* 에이전트 활동 로그 */}
            <motion.div variants={item}>
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Database className="h-5 w-5 text-primary" />
                            에이전트 활동 로그
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-2">
                            <div className="flex items-center gap-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                                <CheckCircle className="h-4 w-4 text-emerald-500 shrink-0" />
                                <div className="flex-1">
                                    <div className="text-sm font-medium">Sourcing Agent</div>
                                    <div className="text-xs text-muted-foreground">새로운 상품 후보 5개 발견</div>
                                </div>
                                <div className="text-xs text-muted-foreground">2분 전</div>
                            </div>
                            <div className="flex items-center gap-3 p-3 rounded-lg bg-primary/10 border border-primary/20">
                                <Activity className="h-4 w-4 text-primary shrink-0" />
                                <div className="flex-1">
                                    <div className="text-sm font-medium">Processing Agent</div>
                                    <div className="text-xs text-muted-foreground">상품 데이터 최적화 완료</div>
                                </div>
                                <div className="text-xs text-muted-foreground">5분 전</div>
                            </div>
                            <div className="flex items-center gap-3 p-3 rounded-lg bg-blue-500/10 border border-blue-500/20">
                                <TrendingUp className="h-4 w-4 text-blue-500 shrink-0" />
                                <div className="flex-1">
                                    <div className="text-sm font-medium">Analysis Agent</div>
                                    <div className="text-xs text-muted-foreground">주간 판매 분석 리포트 생성</div>
                                </div>
                                <div className="text-xs text-muted-foreground">10분 전</div>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </motion.div>
        </motion.div>
    );
}
