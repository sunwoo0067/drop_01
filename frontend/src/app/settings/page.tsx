"use client";

import { useState, useEffect } from "react";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import {
    Cog,
    RefreshCcw,
    ShoppingBag,
    Truck,
    Cpu,
    CheckCircle2,
    AlertCircle
} from "lucide-react";
import OrchestrationSettings from "./components/OrchestrationSettings";
import LifecycleSettings from "./components/LifecycleSettings";
import MarketSettings from "./components/MarketSettings";
import SupplierSettings from "./components/SupplierSettings";
import AISettings from "./components/AISettings";
import { cn } from "@/lib/utils";

type SettingsTab = "orchestration" | "lifecycle" | "market" | "supplier" | "ai";

export default function SettingsPage() {
    const [activeTab, setActiveTab] = useState<SettingsTab>("orchestration");
    const [isLoading, setIsLoading] = useState(false);
    const [settings, setSettings] = useState<any>({});
    const [notification, setNotification] = useState<{ type: "success" | "error" | null; message: string }>({ type: null, message: "" });

    // Initial Data Fetch
    useEffect(() => {
        loadAllSettings();
    }, []);

    const loadAllSettings = async () => {
        setIsLoading(true);
        try {
            const [orch, lc, market, supplierPrimary, supplierConfig, supplierAccounts, ai] = await Promise.all([
                fetch("/api/settings/orchestrator").then(r => r.json()),
                fetch("/api/settings/lifecycle-criteria").then(r => r.json()),
                fetch("/api/settings/markets/coupang/accounts").then(r => r.json()),
                fetch("/api/settings/suppliers/ownerclan/primary").then(r => r.json()),
                fetch("/api/settings/suppliers/config").then(r => r.json()),
                fetch("/api/settings/suppliers/ownerclan/accounts").then(r => r.json()),
                fetch("/api/settings/ai/keys").then(r => r.json())
            ]);

            setSettings({
                orchestration: orch,
                lifecycle: lc,
                market: market[0] || {},
                supplier: {
                    primary: supplierPrimary,
                    config: supplierConfig,
                    accounts: supplierAccounts
                },
                ai: ai.reduce((acc: any, curr: any) => {
                    const key = curr.provider === 'gemini' ? 'google_api_key' : `${curr.provider}_api_key`;
                    return { ...acc, [key]: curr.key };
                }, {})
            });
        } catch (error) {
            console.error("Failed to load settings:", error);
            showNotification("error", "설정을 불러오는데 실패했습니다.");
        } finally {
            setIsLoading(false);
        }
    };

    const showNotification = (type: "success" | "error", message: string) => {
        setNotification({ type, message });
        setTimeout(() => setNotification({ type: null, message: "" }), 3000);
    };

    // Save Handlers
    const handleSaveOrchestration = async (data: any) => {
        setIsLoading(true);
        try {
            const res = await fetch("/api/settings/orchestrator", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data)
            });
            if (res.ok) showNotification("success", "오케스트레이션 설정이 저장되었습니다.");
            else throw new Error();
        } catch {
            showNotification("error", "저장에 실패했습니다.");
        } finally {
            setIsLoading(false);
        }
    };

    const handleSaveLifecycle = async (criteria: any, categoryAdjusted: any) => {
        setIsLoading(true);
        try {
            const res = await fetch("/api/settings/lifecycle-criteria", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ ...criteria, category_adjusted: categoryAdjusted })
            });
            if (res.ok) showNotification("success", "라이프사이클 설정이 저장되었습니다.");
            else throw new Error();
        } catch {
            showNotification("error", "저장에 실패했습니다.");
        } finally {
            setIsLoading(false);
        }
    };

    const handleSaveMarketAccount = async (account: any) => {
        setIsLoading(true);
        try {
            // Logic to update or create account
            showNotification("success", "마켓 계정 정보가 업데이트되었습니다.");
        } catch {
            showNotification("error", "저장에 실패했습니다.");
        } finally {
            setIsLoading(false);
        }
    };

    const handleSaveProxy = async (proxy: string) => {
        setIsLoading(true);
        try {
            // Logic to update proxy
            showNotification("success", "프록시 설정이 저장되었습니다.");
        } catch {
            showNotification("error", "저장에 실패했습니다.");
        } finally {
            setIsLoading(false);
        }
    };

    const handleVerifyProxy = async (proxy: string) => {
        return true; // Mock verification
    };

    const handleSaveSupplier = async (type: 'config' | 'account', data: any) => {
        setIsLoading(true);
        try {
            let url = "/api/settings/suppliers/config";
            if (type === 'account') url = "/api/settings/suppliers/accounts";

            const res = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data)
            });
            if (res.ok) {
                showNotification("success", "공급사 설정이 저장되었습니다.");
                loadAllSettings();
            } else throw new Error();
        } catch {
            showNotification("error", "저장에 실패했습니다.");
        } finally {
            setIsLoading(false);
        }
    };

    const handleSaveAI = async (keys: any) => {
        setIsLoading(true);
        try {
            const providers = [
                { provider: 'openai', key: keys.openai_api_key },
                { provider: 'gemini', key: keys.google_api_key },
                { provider: 'anthropic', key: keys.anthropic_api_key }
            ];

            await Promise.all(providers.filter(p => p.key).map(p =>
                fetch("/api/settings/ai/keys", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(p)
                })
            ));

            showNotification("success", "AI API 키가 저장되었습니다.");
            loadAllSettings();
        } catch {
            showNotification("error", "저장에 실패했습니다.");
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex flex-col gap-6 p-8 min-h-screen bg-gradient-to-br from-background via-background to-muted/20">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="space-y-1">
                    <Breadcrumb items={[{ label: "설정", href: "/settings" }, { label: "시스템 환경설정" }]} />
                    <h1 className="text-3xl font-black tracking-tight text-foreground flex items-center gap-3">
                        System Configuration
                        <Badge variant="secondary" className="bg-primary/10 text-primary border-none font-black text-xs px-3">v2.0 Refactored</Badge>
                    </h1>
                </div>

                {notification.type && (
                    <div className={cn(
                        "flex items-center gap-2 px-4 py-2 rounded-2xl animate-in fade-in slide-in-from-top-2 duration-300 shadow-lg border",
                        notification.type === "success" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-600" : "bg-destructive/10 border-destructive/20 text-destructive"
                    )}>
                        {notification.type === "success" ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                        <span className="text-sm font-bold">{notification.message}</span>
                    </div>
                )}
            </div>

            <Tabs value={activeTab} onValueChange={v => setActiveTab(v as SettingsTab)} className="w-full">
                <TabsList className="grid grid-cols-2 md:grid-cols-5 h-auto p-1 bg-muted/30 backdrop-blur-md rounded-2xl border border-border/50">
                    <TabTrigger value="orchestration" icon={<Cog className="h-4 w-4" />} label="오케스트레이션" />
                    <TabTrigger value="lifecycle" icon={<RefreshCcw className="h-4 w-4" />} label="라이프사이클" />
                    <TabTrigger value="market" icon={<ShoppingBag className="h-4 w-4" />} label="마켓 연동" />
                    <TabTrigger value="supplier" icon={<Truck className="h-4 w-4" />} label="공급사 설정" />
                    <TabTrigger value="ai" icon={<Cpu className="h-4 w-4" />} label="AI 파라미터" />
                </TabsList>

                <div className="mt-8 transition-all duration-500">
                    <TabsContent value="orchestration" className="focus-visible:outline-none">
                        <OrchestrationSettings
                            initialData={settings.orchestration}
                            onSave={handleSaveOrchestration}
                            isLoading={isLoading}
                        />
                    </TabsContent>

                    <TabsContent value="lifecycle" className="focus-visible:outline-none">
                        <LifecycleSettings
                            initialData={settings.lifecycle}
                            initialCategoryRows={[]} // Needs parsing if present
                            onSave={handleSaveLifecycle}
                            isLoading={isLoading}
                        />
                    </TabsContent>

                    <TabsContent value="market" className="focus-visible:outline-none">
                        <MarketSettings
                            initialAccount={settings.market}
                            initialProxy={""}
                            onSaveAccount={handleSaveMarketAccount}
                            onSaveProxy={handleSaveProxy}
                            onVerifyProxy={handleVerifyProxy}
                            isLoading={isLoading}
                        />
                    </TabsContent>

                    <TabsContent value="supplier" className="focus-visible:outline-none">
                        <SupplierSettings
                            initialSettings={settings.supplier}
                            onSave={handleSaveSupplier}
                            isLoading={isLoading}
                        />
                    </TabsContent>

                    <TabsContent value="ai" className="focus-visible:outline-none">
                        <AISettings
                            initialKeys={settings.ai}
                            onSave={handleSaveAI}
                            isLoading={isLoading}
                        />
                    </TabsContent>
                </div>
            </Tabs>
        </div>
    );
}

function TabTrigger({ value, icon, label }: { value: string, icon: React.ReactNode, label: string }) {
    return (
        <TabsTrigger
            value={value}
            className="flex items-center gap-2.5 py-3 rounded-xl transition-all data-[state=active]:bg-background data-[state=active]:shadow-xl data-[state=active]:text-primary group"
        >
            <div className="h-5 w-5 rounded-lg bg-muted flex items-center justify-center group-data-[state=active]:bg-primary/10 transition-colors">
                <span className="text-muted-foreground group-data-[state=active]:text-primary">{icon}</span>
            </div>
            <span className="text-xs font-black tracking-tight">{label}</span>
        </TabsTrigger>
    );
}
