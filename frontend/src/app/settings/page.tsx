"use client";

import { useState } from "react";
import { Settings, Save, AlertTriangle, Lock } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Breadcrumb, BreadcrumbItem } from "@/components/ui/Breadcrumb";

type SettingsTab = "orchestration" | "market" | "supplier" | "ai";

export default function SettingsPage() {
    const [activeTab, setActiveTab] = useState<SettingsTab>("orchestration");
    const [isLoading, setIsLoading] = useState(false);
    const [notification, setNotification] = useState<{ type: "success" | "error" | null; message: string }>({ type: null, message: "" });

    const [orchestratorForm, setOrchestratorForm] = useState({
        listing_limit: 15000,
        sourcing_keyword_limit: 30,
        continuous_mode: false
    });

    const saveOrchestratorSettings = async () => {
        setIsLoading(true);
        try {
            const response = await fetch('/api/settings/orchestrator', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(orchestratorForm)
            });
            
            if (response.ok) {
                setNotification({ type: "success", message: "오케스트레이션 설정이 저장되었습니다." });
            } else {
                setNotification({ type: "error", message: "설정 저장에 실패했습니다." });
            }
        } catch (error) {
            console.error("Failed to save orchestrator settings", error);
            setNotification({ type: "error", message: "설정 저장에 실패했습니다." });
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="space-y-3">
            <Breadcrumb
                items={[
                    { label: "설정" }
                ]}
            />

            <div className="flex items-center gap-1 px-4 py-1.5 border-b border-border bg-card">
                <button
                    className={`px-2 py-1 text-[10px] font-medium border-b-2 transition-colors ${activeTab === "orchestration" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                    onClick={() => setActiveTab("orchestration")}
                >
                    오케스트레이션
                </button>
                <button
                    className={`px-2 py-1 text-[10px] font-medium border-b-2 transition-colors ${activeTab === "market" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                    onClick={() => setActiveTab("market")}
                >
                    마켓
                </button>
                <button
                    className={`px-2 py-1 text-[10px] font-medium border-b-2 transition-colors ${activeTab === "supplier" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                    onClick={() => setActiveTab("supplier")}
                >
                    공급사
                </button>
                <button
                    className={`px-2 py-1 text-[10px] font-medium border-b-2 transition-colors ${activeTab === "ai" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                    onClick={() => setActiveTab("ai")}
                >
                    AI
                </button>
            </div>

            {notification.message && (
                <div className={`px-4 py-1 text-[10px] border-b ${notification.type === "success" ? "border-success/50 bg-success/5" : "border-destructive/50 bg-destructive/5"}`}>
                    {notification.message}
                </div>
            )}

            <div className="px-4 py-2 space-y-2">
                {activeTab === "orchestration" && (
                    <Card className="border border-border">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-xs flex items-center gap-1">
                                <Lock className="h-3 w-3 text-primary" />
                                오케스트레이션 설정
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2.5">
                            <div className="grid gap-2 grid-cols-1 md:grid-cols-2">
                                <div className="space-y-1">
                                    <label className="text-[10px] font-medium text-muted-foreground">일일 등록 한도</label>
                                    <Input
                                        type="number"
                                        value={orchestratorForm.listing_limit}
                                        onChange={(e) => setOrchestratorForm({ ...orchestratorForm, listing_limit: parseInt(e.target.value) || 0 })}
                                        placeholder="15000"
                                        size="sm"
                                    />
                                    <p className="text-[9px] text-muted-foreground">가공 및 등록 대상 상품의 최대 수량입니다. (권장: 5,000 ~ 20,000)</p>
                                </div>
                                <div className="space-y-1">
                                    <label className="text-[10px] font-medium text-muted-foreground">소싱 키워드 제한</label>
                                    <Input
                                        type="number"
                                        value={orchestratorForm.sourcing_keyword_limit}
                                        onChange={(e) => setOrchestratorForm({ ...orchestratorForm, sourcing_keyword_limit: parseInt(e.target.value) || 0 })}
                                        placeholder="30"
                                        size="sm"
                                    />
                                    <p className="text-[9px] text-muted-foreground">소싱에 사용할 키워드 수량입니다. (권장: 10 ~ 50)</p>
                                </div>
                            </div>

                            <div className="space-y-1.5">
                                <label className="flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground cursor-pointer">
                                    <input
                                        type="checkbox"
                                        id="continuous_mode"
                                        className="w-3 h-3"
                                        checked={orchestratorForm.continuous_mode}
                                        onChange={(e) => setOrchestratorForm({ ...orchestratorForm, continuous_mode: e.target.checked })}
                                    />
                                    지속 등록 모드 (Continuous Listing)
                                </label>
                                <p className="text-[9px] text-muted-foreground">사이클 완료 후에도 백그라운드에서 상품 등록 작업을 계속 유지합니다.</p>
                            </div>

                            <div className="p-2 border border-warning/50 rounded-sm bg-warning/5">
                                <div className="flex items-start gap-1.5">
                                    <AlertTriangle className="h-3 w-3 text-warning flex-shrink-0" />
                                    <p className="text-[9px] text-warning-foreground">
                                        <span className="font-semibold">주의:</span> 너무 많은 상품을 한 번에 등록하면 마켓 API 제한으로 인해 계정이 일시 정지될 수 있습니다.
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                        <CardFooter className="flex justify-end pt-2 border-t border-border/50">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setOrchestratorForm({
                                    listing_limit: 15000,
                                    sourcing_keyword_limit: 30,
                                    continuous_mode: false
                                })}
                            >
                                초기화
                            </Button>
                            <Button
                                onClick={saveOrchestratorSettings}
                                disabled={isLoading}
                                size="sm"
                            >
                                {isLoading ? <span className="flex items-center gap-1">저장 중...</span> : <span className="flex items-center gap-1"><Save className="h-3 w-3" />저장</span>}
                            </Button>
                        </CardFooter>
                    </Card>
                )}

                {activeTab !== "orchestration" && (
                    <div className="border border-border rounded-sm bg-card p-6 flex flex-col items-center justify-center">
                        <div className="text-center">
                            <Settings className="h-6 w-6 mx-auto mb-2 text-muted-foreground" />
                            <p className="text-xs text-muted-foreground">해당 설정 탭은 현재 개발 중입니다.</p>
                            <p className="text-[9px] text-muted-foreground">다른 탭을 선택해주세요.</p>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
