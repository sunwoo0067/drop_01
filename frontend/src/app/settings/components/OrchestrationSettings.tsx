"use client";

import { useState, useEffect } from "react";
import { Lock, Save, AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { toInt } from "../utils";

interface OrchestratorForm {
    listing_limit: number;
    sourcing_keyword_limit: number;
    sourcing_import_limit: number;
    initial_processing_batch: number;
    processing_batch_size: number;
    listing_concurrency: number;
    listing_batch_limit: number;
    backfill_approve_enabled: boolean;
    backfill_approve_limit: number;
    continuous_mode: boolean;
}

interface OrchestrationSettingsProps {
    initialData?: OrchestratorForm;
    onSave: (data: OrchestratorForm) => Promise<void>;
    isLoading?: boolean;
}

const defaultValues: OrchestratorForm = {
    listing_limit: 15000,
    sourcing_keyword_limit: 30,
    sourcing_import_limit: 15000,
    initial_processing_batch: 100,
    processing_batch_size: 50,
    listing_concurrency: 5,
    listing_batch_limit: 100,
    backfill_approve_enabled: true,
    backfill_approve_limit: 2000,
    continuous_mode: false
};

export default function OrchestrationSettings({ initialData, onSave, isLoading }: OrchestrationSettingsProps) {
    const [form, setForm] = useState<OrchestratorForm>(initialData || defaultValues);

    useEffect(() => {
        if (initialData) {
            setForm(initialData);
        }
    }, [initialData]);

    const handleReset = () => {
        setForm(defaultValues);
    };

    return (
        <Card className="border border-border bg-card/50 backdrop-blur-sm shadow-sm overflow-hidden">
            <CardHeader className="pb-4 border-b border-border/50 bg-muted/5">
                <CardTitle className="text-sm font-black flex items-center gap-2">
                    <div className="h-6 w-6 rounded-lg bg-primary/10 flex items-center justify-center">
                        <Lock className="h-3.5 w-3.5 text-primary" />
                    </div>
                    오케스트레이션 핵심 설정
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6 pt-6">
                <div className="grid gap-6 grid-cols-1 lg:grid-cols-2">
                    {/* 소싱 전략 */}
                    <div className="space-y-4 rounded-2xl border border-border/50 bg-muted/20 p-5 transition-all hover:bg-muted/30">
                        <div className="text-xs font-black text-foreground/70 uppercase tracking-widest flex items-center gap-2">
                            <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                            소싱 전략 파라미터
                        </div>
                        <div className="grid gap-4 md:grid-cols-2">
                            <div className="space-y-1.5">
                                <label className="text-[11px] font-bold text-muted-foreground ml-1">소싱 키워드 제한</label>
                                <Input
                                    type="number"
                                    value={form.sourcing_keyword_limit}
                                    onChange={(e) => setForm({ ...form, sourcing_keyword_limit: toInt(e.target.value, 0) })}
                                    className="h-9 font-mono font-bold"
                                />
                                <p className="text-[10px] text-muted-foreground/70 ml-1">전체 소싱에 사용할 키워드 수량</p>
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[11px] font-bold text-muted-foreground ml-1">후보 전환 한도</label>
                                <Input
                                    type="number"
                                    value={form.sourcing_import_limit}
                                    onChange={(e) => setForm({ ...form, sourcing_import_limit: toInt(e.target.value, 0) })}
                                    className="h-9 font-mono font-bold"
                                />
                                <p className="text-[10px] text-muted-foreground/70 ml-1">수집 데이터 → 후보 전환 최대 수량</p>
                            </div>
                        </div>
                        <div className="pt-2 border-t border-border/50">
                            <label className="flex items-center gap-3 text-[11px] font-bold text-foreground cursor-pointer group">
                                <div className={cn(
                                    "h-4 w-4 rounded border transition-all flex items-center justify-center",
                                    form.backfill_approve_enabled ? "bg-primary border-primary" : "bg-background border-border"
                                )}>
                                    <input
                                        type="checkbox"
                                        className="hidden"
                                        checked={form.backfill_approve_enabled}
                                        onChange={(e) => setForm({ ...form, backfill_approve_enabled: e.target.checked })}
                                    />
                                    {form.backfill_approve_enabled && <div className="h-1.5 w-1.5 rounded-full bg-white" />}
                                </div>
                                목표 수량 부족 시 자동 승인 활성화
                            </label>
                            {form.backfill_approve_enabled && (
                                <div className="mt-3 grid gap-2 md:grid-cols-2 animate-in slide-in-from-top-1 duration-200">
                                    <div className="space-y-1.5">
                                        <label className="text-[11px] font-bold text-muted-foreground ml-1">자동 승인 일일 상한</label>
                                        <Input
                                            type="number"
                                            value={form.backfill_approve_limit}
                                            onChange={(e) => setForm({ ...form, backfill_approve_limit: toInt(e.target.value, 0) })}
                                            className="h-9 font-mono font-bold border-primary/20 bg-primary/5"
                                        />
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* 가공 파이프라인 */}
                    <div className="space-y-4 rounded-2xl border border-border/50 bg-muted/20 p-5 transition-all hover:bg-muted/30">
                        <div className="text-xs font-black text-foreground/70 uppercase tracking-widest flex items-center gap-2">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                            가공 엔진 파이프라인
                        </div>
                        <div className="grid gap-4 md:grid-cols-2">
                            <div className="space-y-1.5">
                                <label className="text-[11px] font-bold text-muted-foreground ml-1">초기 동기 가공 배치</label>
                                <Input
                                    type="number"
                                    value={form.initial_processing_batch}
                                    onChange={(e) => setForm({ ...form, initial_processing_batch: toInt(e.target.value, 0) })}
                                    className="h-9 font-mono font-bold"
                                />
                                <p className="text-[10px] text-muted-foreground/70 ml-1">사이클 시작 직후 즉시 처리량</p>
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[11px] font-bold text-muted-foreground ml-1">지속 백그라운드 배치</label>
                                <Input
                                    type="number"
                                    value={form.processing_batch_size}
                                    onChange={(e) => setForm({ ...form, processing_batch_size: toInt(e.target.value, 0) })}
                                    className="h-9 font-mono font-bold"
                                />
                                <p className="text-[10px] text-muted-foreground/70 ml-1">워커가 처리할 비동기 배치 단위</p>
                            </div>
                        </div>
                    </div>

                    {/* 등록 파이프라인 */}
                    <div className="space-y-4 rounded-2xl border border-border/50 bg-muted/20 p-5 transition-all hover:bg-muted/30 lg:col-span-2">
                        <div className="text-xs font-black text-foreground/70 uppercase tracking-widest flex items-center gap-2">
                            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                            마켓 등록 오케스트레이션
                        </div>
                        <div className="grid gap-4 md:grid-cols-4">
                            <div className="space-y-1.5 md:col-span-2">
                                <label className="text-[11px] font-bold text-muted-foreground ml-1">일일 상품 등록 한도</label>
                                <Input
                                    type="number"
                                    value={form.listing_limit}
                                    onChange={(e) => setForm({ ...form, listing_limit: toInt(e.target.value, 0) })}
                                    className="h-10 font-mono font-black text-primary text-base"
                                />
                                <p className="text-[10px] text-muted-foreground/70 ml-1">24시간 내 가공 및 등록할 전체 목표 수량</p>
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[11px] font-bold text-muted-foreground ml-1">API 병렬 동시성</label>
                                <Input
                                    type="number"
                                    value={form.listing_concurrency}
                                    onChange={(e) => setForm({ ...form, listing_concurrency: toInt(e.target.value, 1) })}
                                    className="h-10 font-mono font-bold"
                                />
                                <p className="text-[10px] text-muted-foreground/70 ml-1">마켓별 동시 요청 수</p>
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-[11px] font-bold text-muted-foreground ml-1">배치 등록 수량</label>
                                <Input
                                    type="number"
                                    value={form.listing_batch_limit}
                                    onChange={(e) => setForm({ ...form, listing_batch_limit: toInt(e.target.value, 0) })}
                                    className="h-10 font-mono font-bold"
                                />
                                <p className="text-[10px] text-muted-foreground/70 ml-1">자동 모드 1회당 등록량</p>
                            </div>
                        </div>

                        <div className="pt-2 flex flex-col md:flex-row md:items-center justify-between gap-4">
                            <label className="flex items-center gap-3 text-[11px] font-bold text-foreground cursor-pointer group">
                                <div className={cn(
                                    "h-10 w-20 rounded-full border-2 transition-all relative",
                                    form.continuous_mode ? "bg-primary border-primary" : "bg-muted border-border"
                                )}>
                                    <input
                                        type="checkbox"
                                        className="hidden"
                                        checked={form.continuous_mode}
                                        onChange={(e) => setForm({ ...form, continuous_mode: e.target.checked })}
                                    />
                                    <div className={cn(
                                        "absolute top-1 h-7 w-7 rounded-full bg-white shadow-lg transition-all",
                                        form.continuous_mode ? "left-[calc(100%-2.25rem)]" : "left-1"
                                    )} />
                                </div>
                                <div className="flex flex-col">
                                    <span>지속 등록 모드 (Continuous Listing)</span>
                                    <span className="text-[10px] font-medium text-muted-foreground">사이클 완료 후에도 유휴 시간에 백그라운드 등록 유지</span>
                                </div>
                            </label>

                            <div className="flex items-center gap-2 p-3 bg-amber-500/5 border border-amber-500/10 rounded-xl">
                                <AlertTriangle className="h-4 w-4 text-amber-500" />
                                <p className="text-[11px] text-amber-700/80 font-medium leading-tight">
                                    등록 동시성 값이 너무 높으면 마켓 API 제한으로 <br />계정이 일시 정지될 수 있으니 주의하세요.
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </CardContent>
            <CardFooter className="flex justify-between items-center py-6 px-8 border-t border-border/50 bg-muted/5">
                <Button
                    variant="ghost"
                    size="sm"
                    className="h-10 rounded-xl font-bold text-muted-foreground hover:bg-destructive/5 hover:text-destructive transition-all"
                    onClick={handleReset}
                >
                    <RotateCcw className="mr-2 h-4 w-4" />
                    기본값으로 초기화
                </Button>
                <div className="flex items-center gap-3">
                    <Button
                        size="lg"
                        className="h-11 rounded-xl font-black px-10 shadow-lg shadow-primary/20 transition-all hover:scale-105 active:scale-95"
                        onClick={() => onSave(form)}
                        disabled={isLoading}
                    >
                        {isLoading ? (
                            <span className="flex items-center gap-2">
                                <div className="h-4 w-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                                저장 중...
                            </span>
                        ) : (
                            <span className="flex items-center gap-2">
                                <Save className="h-4 w-4" />
                                오케스트레이션 설정 변경 사항 반영
                            </span>
                        )}
                    </Button>
                </div>
            </CardFooter>
        </Card>
    );
}

import { cn } from "@/lib/utils";
