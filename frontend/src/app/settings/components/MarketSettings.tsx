"use client";

import { useState, useEffect } from "react";
import {
    ShoppingBag,
    Save,
    Shield,
    Globe,
    Zap,
    Lock,
    User,
    Building2,
    Server,
    CheckCircle2,
    XCircle
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

interface MarketAccount {
    coupang_login_id: string;
    coupang_login_pw: string;
    coupang_vendor_id: string;
}

interface MarketSettingsProps {
    initialAccount?: MarketAccount;
    initialProxy?: string;
    onSaveAccount: (account: MarketAccount) => Promise<void>;
    onSaveProxy: (proxy: string) => Promise<void>;
    onVerifyProxy: (proxy: string) => Promise<boolean>;
    isLoading?: boolean;
}

export default function MarketSettings({
    initialAccount,
    initialProxy,
    onSaveAccount,
    onSaveProxy,
    onVerifyProxy,
    isLoading
}: MarketSettingsProps) {
    const [account, setAccount] = useState<MarketAccount>(initialAccount || {
        coupang_login_id: "",
        coupang_login_pw: "",
        coupang_vendor_id: ""
    });
    const [proxyString, setProxyString] = useState(initialProxy || "");
    const [isVerifyingProxy, setIsVerifyingProxy] = useState(false);
    const [proxyStatus, setProxyStatus] = useState<'idle' | 'success' | 'error'>('idle');

    useEffect(() => {
        if (initialAccount) setAccount(initialAccount);
        if (initialProxy) setProxyString(initialProxy);
    }, [initialAccount, initialProxy]);

    const handleVerifyProxy = async () => {
        setIsVerifyingProxy(true);
        try {
            const success = await onVerifyProxy(proxyString);
            setProxyStatus(success ? 'success' : 'error');
        } catch {
            setProxyStatus('error');
        } finally {
            setIsVerifyingProxy(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Coupang Account */}
                <Card className="border border-border/50 bg-card/50 backdrop-blur-sm shadow-sm overflow-hidden">
                    <CardHeader className="bg-muted/5 border-b border-border/50 pb-4">
                        <CardTitle className="text-sm font-black flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <div className="h-6 w-6 rounded-lg bg-primary/10 flex items-center justify-center">
                                    <ShoppingBag className="h-3.5 w-3.5 text-primary" />
                                </div>
                                쿠팡 마켓 계정 정보
                            </div>
                            <Badge variant="outline" className="text-[10px] border-primary/20 bg-primary/5 text-primary">Active</Badge>
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="p-6 space-y-5">
                        <div className="space-y-4">
                            <InputGroup
                                label="쿠팡 로그인 ID"
                                icon={<User className="h-4 w-4" />}
                                value={account.coupang_login_id}
                                onChange={v => setAccount({ ...account, coupang_login_id: v })}
                                placeholder="Coupang ID"
                            />
                            <InputGroup
                                label="쿠팡 로그인 PW"
                                icon={<Lock className="h-4 w-4" />}
                                type="password"
                                value={account.coupang_login_pw}
                                onChange={v => setAccount({ ...account, coupang_login_pw: v })}
                                placeholder="••••••••"
                            />
                            <InputGroup
                                label="Vendor ID (업체코드)"
                                icon={<Building2 className="h-4 w-4" />}
                                value={account.coupang_vendor_id}
                                onChange={v => setAccount({ ...account, coupang_vendor_id: v })}
                                placeholder="A00XXXXXX"
                            />
                        </div>
                    </CardContent>
                    <CardFooter className="bg-muted/5 border-t border-border/50 py-4 px-6 flex justify-end">
                        <Button
                            size="lg"
                            className="h-10 rounded-xl font-black px-8 shadow-md shadow-primary/10 transition-all hover:scale-105"
                            onClick={() => onSaveAccount(account)}
                            disabled={isLoading}
                        >
                            {isLoading ? "저장 중..." : "계정 정보 업데이트"}
                        </Button>
                    </CardFooter>
                </Card>

                {/* Proxy Settings */}
                <Card className="border border-border/50 bg-card/50 backdrop-blur-sm shadow-sm overflow-hidden">
                    <CardHeader className="bg-muted/5 border-b border-border/50 pb-4">
                        <CardTitle className="text-sm font-black flex items-center gap-2">
                            <div className="h-6 w-6 rounded-lg bg-orange-500/10 flex items-center justify-center">
                                <Globe className="h-3.5 w-3.5 text-orange-500" />
                            </div>
                            네트워크 프록시 설정
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="p-6 space-y-6">
                        <div className="space-y-2">
                            <div className="flex items-center justify-between mb-1">
                                <label className="text-[11px] font-bold text-muted-foreground ml-1 flex items-center gap-1.5">
                                    <Server className="h-3 w-3" />
                                    Proxy Server String
                                </label>
                                {proxyStatus === 'success' && <span className="text-[10px] text-emerald-500 font-bold flex items-center gap-1"><CheckCircle2 className="h-3 w-3" />연결 성공</span>}
                                {proxyStatus === 'error' && <span className="text-[10px] text-destructive font-bold flex items-center gap-1"><XCircle className="h-3 w-3" />연결 실패</span>}
                            </div>
                            <Input
                                value={proxyString}
                                onChange={e => setProxyString(e.target.value)}
                                placeholder="http://user:pass@host:port"
                                className="h-11 font-mono text-xs bg-muted/20 border-border/50 rounded-2xl"
                            />
                            <p className="text-[10px] text-muted-foreground/60 leading-relaxed px-1">
                                쿠팡 API 요청 시 IP 차단을 방지하기 위한 프록시를 설정합니다. <br />
                                <span className="text-orange-500/80 font-bold">주의:</span> 잘못된 프록시 설정 시 동기화가 중단될 수 있습니다.
                            </p>
                        </div>

                        <Button
                            variant="outline"
                            className="w-full h-11 rounded-2xl font-bold border-dashed border-2 hover:bg-muted/30"
                            onClick={handleVerifyProxy}
                            disabled={isVerifyingProxy || !proxyString}
                        >
                            {isVerifyingProxy ? (
                                <span className="flex items-center gap-2">
                                    <div className="h-3.5 w-3.5 border-2 border-primary/20 border-t-primary rounded-full animate-spin" />
                                    연결 상태 확인 중...
                                </span>
                            ) : (
                                <span className="flex items-center gap-2 text-primary">
                                    <Zap className="h-3.5 w-3.5" />
                                    프록시 서버 연결 테스트
                                </span>
                            )}
                        </Button>
                    </CardContent>
                    <CardFooter className="bg-muted/5 border-t border-border/50 py-4 px-6 flex justify-end">
                        <Button
                            variant="secondary"
                            size="lg"
                            className="h-10 rounded-xl font-black px-8 transition-all"
                            onClick={() => onSaveProxy(proxyString)}
                            disabled={isLoading}
                        >
                            프록시 설정 반영
                        </Button>
                    </CardFooter>
                </Card>
            </div>

            {/* Market Sync Features */}
            <Card className="border border-border/50 bg-card/50 backdrop-blur-sm">
                <CardHeader className="pb-4">
                    <CardTitle className="text-sm font-black flex items-center gap-2">
                        <Shield className="h-4 w-4 text-emerald-500" />
                        마켓 보안 및 연동 기능
                    </CardTitle>
                </CardHeader>
                <CardContent className="pb-6">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <SyncFeatureItem
                            label="자동 보안 문자 우회"
                            description="AI를 활용하여 쿠팡 로그인 시 발생하는 캡차를 자동으로 해결합니다."
                            active
                        />
                        <SyncFeatureItem
                            label="지능형 간격 동기화"
                            description="API 호출 부하를 자동으로 분산하여 마켓 계정의 안전성을 확보합니다."
                            active
                        />
                        <SyncFeatureItem
                            label="재등록 자동 복구"
                            description="반려 상품의 원인을 분석하여 자동으로 수정한 후 재등록을 시도합니다."
                            active
                        />
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}

function InputGroup({ label, icon, value, onChange, placeholder, type = "text" }: { label: string, icon: React.ReactNode, value: string, onChange: (v: string) => void, placeholder: string, type?: string }) {
    return (
        <div className="space-y-2">
            <label className="text-[11px] font-bold text-muted-foreground ml-1">{label}</label>
            <div className="relative group">
                <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground/50 group-focus-within:text-primary transition-colors">
                    {icon}
                </div>
                <Input
                    type={type}
                    value={value}
                    onChange={e => onChange(e.target.value)}
                    placeholder={placeholder}
                    className="pl-11 h-11 bg-muted/20 border-border/50 rounded-2xl font-medium focus:ring-1 transition-all"
                />
            </div>
        </div>
    );
}

function SyncFeatureItem({ label, description, active }: { label: string, description: string, active: boolean }) {
    return (
        <div className="p-4 rounded-2xl border border-border/40 bg-muted/10 space-y-2">
            <div className="flex items-center justify-between">
                <span className="text-[11px] font-black text-foreground">{label}</span>
                <div className={cn("h-2 w-2 rounded-full", active ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" : "bg-muted")} />
            </div>
            <p className="text-[10px] text-muted-foreground/70 leading-normal">
                {description}
            </p>
        </div>
    );
}
