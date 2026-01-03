"use client";

import { useState, useEffect } from "react";
import {
    Truck,
    Save,
    Key,
    Percent,
    Coins,
    Info,
    RefreshCw,
    ExternalLink,
    AlertCircle,
    Plus,
    Activity,
    Shield,
    CheckCircle2,
    XCircle,
    User,
    Lock
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/Tabs";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { toInt, toFloat } from "../utils";
import { cn } from "@/lib/utils";

interface SupplierConfig {
    margin_rate: number;
    delivery_fee: number;
    sync_auto_enabled: boolean;
}

interface SupplierAccount {
    id: string;
    username: string;
    userType: string;
    isActive: boolean;
    isPrimary: boolean;
    tokenExpiresAt?: string;
    updatedAt?: string;
}

interface SupplierSettingsProps {
    initialSettings?: {
        config: SupplierConfig;
        accounts: SupplierAccount[];
    };
    onSave: (type: 'config' | 'account', data: any) => Promise<void>;
    isLoading?: boolean;
}

export default function SupplierSettings({ initialSettings, onSave, isLoading }: SupplierSettingsProps) {
    const [activeTab, setActiveTab] = useState("config");
    const [config, setConfig] = useState<SupplierConfig>(initialSettings?.config || {
        margin_rate: 0.15,
        delivery_fee: 3000,
        sync_auto_enabled: true
    });

    // Account Modal State
    const [isAccountModalOpen, setIsAccountModalOpen] = useState(false);
    const [newAccountData, setNewAccountData] = useState({
        user_type: "seller",
        username: "",
        password: "",
        set_primary: true,
        is_active: true
    });

    useEffect(() => {
        if (initialSettings?.config) setConfig(initialSettings.config);
    }, [initialSettings]);

    const handleSaveConfig = () => {
        onSave('config', config);
    };

    const handleAddAccount = () => {
        setNewAccountData({
            user_type: "seller",
            username: "",
            password: "",
            set_primary: true,
            is_active: true
        });
        setIsAccountModalOpen(true);
    };

    const handleSaveAccount = async () => {
        await onSave('account', newAccountData);
        setIsAccountModalOpen(false);
    };

    return (
        <div className="space-y-6">
            <Tabs
                value={activeTab}
                onValueChange={setActiveTab}
                className="w-full"
            >
                <TabsList className="w-full max-w-md">
                    <TabsTrigger value="config" label="기본 설정" />
                    <TabsTrigger value="accounts" label="공급사 계정" count={initialSettings?.accounts?.length || 0} />
                    <TabsTrigger value="activity" label="동기화 내역" />
                </TabsList>

                <div className="mt-8">
                    <TabsContent value="config">
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                            {/* Profit & Delivery */}
                            <Card className="lg:col-span-2 border border-border/50 bg-card/50 backdrop-blur-sm shadow-sm overflow-hidden">
                                <CardHeader className="bg-muted/5 border-b border-border/50 pb-4">
                                    <CardTitle className="text-sm font-black flex items-center gap-2">
                                        <div className="h-6 w-6 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                                            <Coins className="h-3.5 w-3.5 text-emerald-500" />
                                        </div>
                                        수익 및 배송 정책
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="p-8 space-y-8">
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                                        <div className="space-y-3">
                                            <label className="text-xs font-black text-muted-foreground flex items-center gap-2">
                                                <Percent className="h-3.5 w-3.5" />
                                                기본 마진율
                                            </label>
                                            <div className="relative">
                                                <Input
                                                    type="number"
                                                    value={config.margin_rate * 100}
                                                    onChange={e => setConfig({ ...config, margin_rate: toFloat(e.target.value, 0) / 100 })}
                                                    className="h-12 font-black text-lg text-primary font-mono pr-10 rounded-2xl bg-muted/20"
                                                />
                                                <span className="absolute right-4 top-1/2 -translate-y-1/2 text-sm font-black text-muted-foreground/40">%</span>
                                            </div>
                                            <p className="text-[10px] text-muted-foreground/60 leading-relaxed italic">
                                                * 공급가 기준 판매제안가 산출 시 적용되는 최소 마진율입니다.
                                            </p>
                                        </div>

                                        <div className="space-y-3">
                                            <label className="text-xs font-black text-muted-foreground flex items-center gap-2">
                                                <Truck className="h-3.5 w-3.5" />
                                                기본 배송비
                                            </label>
                                            <div className="relative">
                                                <Input
                                                    type="number"
                                                    value={config.delivery_fee}
                                                    onChange={e => setConfig({ ...config, delivery_fee: toInt(e.target.value, 0) })}
                                                    className="h-12 font-black text-lg text-primary font-mono pr-10 rounded-2xl bg-muted/20"
                                                />
                                                <span className="absolute right-4 top-1/2 -translate-y-1/2 text-sm font-black text-muted-foreground/40">₩</span>
                                            </div>
                                            <p className="text-[10px] text-muted-foreground/60 leading-relaxed italic">
                                                * 마켓에 등록될 때 기본값으로 사용되는 고정 배송비입니다.
                                            </p>
                                        </div>
                                    </div>

                                    <div className="pt-6 border-t border-border/50">
                                        <div className="flex items-center justify-between p-4 rounded-2xl bg-primary/5 border border-primary/10">
                                            <div className="flex items-center gap-4">
                                                <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center">
                                                    <RefreshCw className={cn("h-5 w-5 text-primary", config.sync_auto_enabled && "animate-spin-slow")} />
                                                </div>
                                                <div className="flex flex-col">
                                                    <span className="text-xs font-black text-foreground">실시간 재고/가격 동기화</span>
                                                    <span className="text-[10px] text-muted-foreground">공급사 변동 시 10분 내 마켓 자동 업데이트</span>
                                                </div>
                                            </div>
                                            <div
                                                onClick={() => setConfig({ ...config, sync_auto_enabled: !config.sync_auto_enabled })}
                                                className={cn(
                                                    "h-7 w-12 rounded-full border transition-all cursor-pointer relative p-1",
                                                    config.sync_auto_enabled ? "bg-primary border-primary" : "bg-muted border-border"
                                                )}
                                            >
                                                <div className={cn(
                                                    "h-5 w-5 rounded-full bg-white shadow-sm transition-all",
                                                    config.sync_auto_enabled ? "ml-5" : "ml-0"
                                                )} />
                                            </div>
                                        </div>
                                    </div>
                                </CardContent>
                                <CardFooter className="bg-muted/5 border-t border-border/50 p-6 flex justify-end">
                                    <Button
                                        size="lg"
                                        className="h-12 rounded-2xl font-black px-12 shadow-xl shadow-primary/10"
                                        onClick={handleSaveConfig}
                                        disabled={isLoading}
                                    >
                                        {isLoading ? "저장 중..." : "시스템 설정 저장"}
                                    </Button>
                                </CardFooter>
                            </Card>

                            <div className="space-y-6">
                                <Card className="border border-amber-500/20 bg-amber-500/5 shadow-none overflow-hidden h-fit">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-xs font-black text-amber-900 flex items-center gap-2">
                                            <Shield className="h-4 w-4" />
                                            Price Guard Policy
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent className="p-5">
                                        <p className="text-[10px] text-amber-800/70 leading-relaxed">
                                            오너클랜의 <span className="font-bold">최저판매가 준수 여부</span>를 자동으로 확인합니다.
                                            설정하신 마진율보다 공급사의 지정 최저가가 높을 경우, 정책에 맞춰 판매가가 자동 상향 조정되어
                                            계정 정지 및 패널티를 미연에 방지합니다.
                                        </p>
                                    </CardContent>
                                </Card>

                                <div className="p-6 rounded-3xl border border-divider bg-card space-y-4">
                                    <h4 className="text-xs font-black">동기화 우선순위</h4>
                                    <div className="space-y-3">
                                        <div className="flex items-center gap-3">
                                            <div className="h-2 w-2 rounded-full bg-emerald-500" />
                                            <span className="text-[10px] font-bold">1순위: 품절/재입고 상태</span>
                                        </div>
                                        <div className="flex items-center gap-3 text-muted-foreground">
                                            <div className="h-2 w-2 rounded-full bg-border" />
                                            <span className="text-[10px] font-bold">2순위: 공급가 변동</span>
                                        </div>
                                        <div className="flex items-center gap-3 text-muted-foreground">
                                            <div className="h-2 w-2 rounded-full bg-border" />
                                            <span className="text-[10px] font-bold">3순위: 상품명/옵션명 수정</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </TabsContent>

                    <TabsContent value="accounts">
                        <Card className="border border-border/50 bg-card/50 backdrop-blur-sm shadow-sm overflow-hidden">
                            <CardHeader className="border-b border-border/50 py-4 flex flex-row items-center justify-between">
                                <CardTitle className="text-sm font-black flex items-center gap-2">
                                    <div className="h-6 w-6 rounded-lg bg-indigo-500/10 flex items-center justify-center">
                                        <User className="h-3.5 w-3.5 text-indigo-500" />
                                    </div>
                                    오너클랜(OwnerClan) 계정 관리
                                </CardTitle>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-9 rounded-xl font-bold border-dashed border-2 flex items-center gap-2"
                                    onClick={handleAddAccount}
                                >
                                    <Plus className="h-4 w-4" />
                                    신규 계정 연동
                                </Button>
                            </CardHeader>
                            <CardContent className="p-0">
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left border-collapse">
                                        <thead className="bg-muted/30 border-b border-border/50">
                                            <tr>
                                                <th className="px-6 py-4 text-[11px] font-black text-muted-foreground uppercase tracking-widest">계정 정보 (ID)</th>
                                                <th className="px-6 py-4 text-[11px] font-black text-muted-foreground uppercase tracking-widest">유형</th>
                                                <th className="px-6 py-4 text-[11px] font-black text-muted-foreground uppercase tracking-widest">상태</th>
                                                <th className="px-6 py-4 text-[11px] font-black text-muted-foreground uppercase tracking-widest">토큰 만료일</th>
                                                <th className="px-6 py-4 text-[11px] font-black text-muted-foreground uppercase tracking-widest text-right">관리</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {initialSettings?.accounts && initialSettings.accounts.length > 0 ? (
                                                initialSettings.accounts.map((acc) => (
                                                    <tr key={acc.id} className="border-b border-border/30 hover:bg-muted/10 transition-colors group">
                                                        <td className="px-6 py-5">
                                                            <div className="flex items-center gap-3">
                                                                <div className="h-10 w-10 rounded-2xl bg-muted/50 flex items-center justify-center border border-border/50 group-hover:border-primary/20 transition-colors">
                                                                    <User className="h-5 w-5 text-muted-foreground" />
                                                                </div>
                                                                <div className="flex flex-col">
                                                                    <span className="text-sm font-black text-foreground">{acc.username}</span>
                                                                    <div className="flex items-center gap-2">
                                                                        {acc.isPrimary && <Badge className="text-[8px] h-4 bg-primary/10 text-primary border-none font-black uppercase">Primary</Badge>}
                                                                        <span className="text-[10px] text-muted-foreground">ID: {acc.id.slice(0, 8)}</span>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </td>
                                                        <td className="px-6 py-5">
                                                            <Badge variant="outline" className="text-[10px] font-bold capitalize bg-background">{acc.userType}</Badge>
                                                        </td>
                                                        <td className="px-6 py-5">
                                                            <div className="flex items-center gap-2">
                                                                <div className={cn("h-1.5 w-1.5 rounded-full shadow-[0_0_8px]", acc.isActive ? "bg-emerald-500 shadow-emerald-500/50" : "bg-slate-300 shadow-slate-300/50")} />
                                                                <span className={cn("text-[11px] font-black", acc.isActive ? "text-emerald-600" : "text-slate-400 text-muted-foreground")}>
                                                                    {acc.isActive ? "Connected" : "Inactive"}
                                                                </span>
                                                            </div>
                                                        </td>
                                                        <td className="px-6 py-5">
                                                            <div className="flex flex-col">
                                                                <span className="text-[11px] font-bold text-muted-foreground">
                                                                    {acc.tokenExpiresAt ? new Date(acc.tokenExpiresAt).toLocaleDateString() : 'N/A'}
                                                                </span>
                                                                <span className="text-[9px] text-muted-foreground/50">Auto-refresh ready</span>
                                                            </div>
                                                        </td>
                                                        <td className="px-6 py-5 text-right">
                                                            <div className="flex items-center justify-end gap-2">
                                                                <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg">
                                                                    <RefreshCw className="h-3.5 w-3.5" />
                                                                </Button>
                                                                <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground">
                                                                    <ExternalLink className="h-3.5 w-3.5" />
                                                                </Button>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                ))
                                            ) : (
                                                <tr>
                                                    <td colSpan={5} className="px-6 py-20 text-center">
                                                        <div className="flex flex-col items-center gap-3 grayscale opacity-30">
                                                            <User className="h-10 w-10 text-muted-foreground" />
                                                            <p className="text-xs font-bold">등록된 공급사 계정이 없습니다.</p>
                                                        </div>
                                                    </td>
                                                </tr>
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                            </CardContent>
                        </Card>
                    </TabsContent>

                    <TabsContent value="activity">
                        <Card className="border border-border/50 bg-card/50 backdrop-blur-sm shadow-sm overflow-hidden">
                            <CardHeader className="border-b border-border/50 py-4">
                                <CardTitle className="text-sm font-black flex items-center gap-2">
                                    <Activity className="h-4 w-4 text-primary" />
                                    실시간 동기화 상태 현황
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="p-8">
                                <div className="flex flex-col items-center justify-center py-20 border-2 border-dashed border-border/50 rounded-3xl bg-muted/20">
                                    <Activity className="h-8 w-8 text-muted-foreground/30 mb-4" />
                                    <p className="text-xs font-bold text-muted-foreground">이 섹션은 현재 개발 중에 있습니다.</p>
                                    <p className="text-[10px] text-muted-foreground/60 mt-1">곧 실시간 작업 로그를 여기서 확인하실 수 있습니다.</p>
                                </div>
                            </CardContent>
                        </Card>
                    </TabsContent>
                </div>
            </Tabs>

            {/* Account Modal */}
            <Modal
                isOpen={isAccountModalOpen}
                onClose={() => setIsAccountModalOpen(false)}
                title="공급사 계정 연동"
                footer={
                    <>
                        <Button variant="ghost" onClick={() => setIsAccountModalOpen(false)}>취소</Button>
                        <Button onClick={handleSaveAccount}>인증 및 연동</Button>
                    </>
                }
            >
                <div className="space-y-6">
                    <div className="space-y-2">
                        <label className="text-xs font-black">계정 유형</label>
                        <div className="grid grid-cols-2 gap-3">
                            <button
                                onClick={() => setNewAccountData({ ...newAccountData, user_type: "seller" })}
                                className={cn(
                                    "p-4 rounded-2xl border text-center transition-all",
                                    newAccountData.user_type === "seller" ? "border-primary bg-primary/5 text-primary" : "border-border bg-muted/20 text-muted-foreground hover:bg-muted/40"
                                )}
                            >
                                <span className="text-xs font-black">판매자 (Seller)</span>
                            </button>
                            <button
                                onClick={() => setNewAccountData({ ...newAccountData, user_type: "vendor" })}
                                className={cn(
                                    "p-4 rounded-2xl border text-center transition-all",
                                    newAccountData.user_type === "vendor" ? "border-primary bg-primary/5 text-primary" : "border-border bg-muted/20 text-muted-foreground hover:bg-muted/40"
                                )}
                            >
                                <span className="text-xs font-black">공급사 (Vendor)</span>
                            </button>
                        </div>
                    </div>

                    <div className="space-y-4">
                        <div className="space-y-2 text-left">
                            <label className="text-xs font-black ml-1">오너클랜 ID</label>
                            <div className="relative group">
                                <User className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/50 group-focus-within:text-primary transition-colors" />
                                <Input
                                    className="pl-11 h-12 rounded-2xl bg-muted/20"
                                    value={newAccountData.username}
                                    onChange={e => setNewAccountData({ ...newAccountData, username: e.target.value })}
                                />
                            </div>
                        </div>
                        <div className="space-y-2 text-left">
                            <label className="text-xs font-black ml-1">오너클랜 Password</label>
                            <div className="relative group">
                                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/50 group-focus-within:text-primary transition-colors" />
                                <Input
                                    type="password"
                                    className="pl-11 h-12 rounded-2xl bg-muted/20"
                                    value={newAccountData.password}
                                    onChange={e => setNewAccountData({ ...newAccountData, password: e.target.value })}
                                />
                            </div>
                        </div>
                    </div>

                    <div className="pt-4 flex items-center gap-4">
                        <div
                            onClick={() => setNewAccountData({ ...newAccountData, set_primary: !newAccountData.set_primary })}
                            className={cn(
                                "h-6 w-11 rounded-full border transition-all cursor-pointer relative p-1",
                                newAccountData.set_primary ? "bg-emerald-500 border-emerald-500" : "bg-muted border-border"
                            )}
                        >
                            <div className={cn(
                                "h-4 w-4 rounded-full bg-white shadow-sm transition-all",
                                newAccountData.set_primary ? "ml-5" : "ml-0"
                            )} />
                        </div>
                        <div className="flex flex-col text-left">
                            <span className="text-xs font-black">대표 계정으로 설정</span>
                            <span className="text-[10px] text-muted-foreground">이 계정을 상품 정보 수집의 기본 소스로 사용합니다.</span>
                        </div>
                    </div>
                </div>
            </Modal>
        </div>
    );
}
