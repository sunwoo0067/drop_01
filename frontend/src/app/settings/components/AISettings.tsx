"use client";

import { useState, useEffect } from "react";
import {
    Cpu,
    Save,
    Key,
    ShieldCheck,
    Sparkles,
    BrainCircuit,
    Zap,
    MessageSquare,
    Eye
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/utils";

interface AIKeys {
    openai_api_key: string;
    google_api_key: string;
    anthropic_api_key: string;
}

interface AISettingsProps {
    initialKeys?: AIKeys;
    onSave: (keys: AIKeys) => Promise<void>;
    isLoading?: boolean;
}

export default function AISettings({ initialKeys, onSave, isLoading }: AISettingsProps) {
    const [keys, setKeys] = useState<AIKeys>(initialKeys || {
        openai_api_key: "",
        google_api_key: "",
        anthropic_api_key: ""
    });

    useEffect(() => {
        if (initialKeys) setKeys(initialKeys);
    }, [initialKeys]);

    return (
        <div className="space-y-6">
            <Card className="border border-border/50 bg-card/50 backdrop-blur-sm shadow-xl overflow-hidden">
                <CardHeader className="bg-muted/5 border-b border-border/50 py-5">
                    <CardTitle className="text-sm font-black flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <div className="h-8 w-8 rounded-xl bg-violet-500/10 flex items-center justify-center">
                                <Cpu className="h-4 w-4 text-violet-500 animate-pulse" />
                            </div>
                            <span>AI 엔진 API 인증 설정</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <ShieldCheck className="h-4 w-4 text-emerald-500" />
                            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-tighter">Securely Encrypted</span>
                        </div>
                    </CardTitle>
                </CardHeader>
                <CardContent className="p-8 space-y-8">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                        {/* OpenAI */}
                        <AIProviderCard
                            name="OpenAI"
                            description="GPT-4o / GPT-3.5 Turbo"
                            icon={<div className="h-10 w-10 flex items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-600"><Sparkles className="h-5 w-5" /></div>}
                            value={keys.openai_api_key}
                            onChange={v => setKeys({ ...keys, openai_api_key: v })}
                            placeholder="sk-proj-..."
                        />
                        {/* Google Gemini */}
                        <AIProviderCard
                            name="Google Gemini"
                            description="Gemini 1.5 Pro / Flash"
                            icon={<div className="h-10 w-10 flex items-center justify-center rounded-2xl bg-blue-500/10 text-blue-600"><BrainCircuit className="h-5 w-5" /></div>}
                            value={keys.google_api_key}
                            onChange={v => setKeys({ ...keys, google_api_key: v })}
                            placeholder="AIzaSyB..."
                        />
                        {/* Anthropic */}
                        <AIProviderCard
                            name="Anthropic"
                            description="Claude 3.5 Sonnet / Haiku"
                            icon={<div className="h-10 w-10 flex items-center justify-center rounded-2xl bg-orange-500/10 text-orange-600"><MessageSquare className="h-5 w-5" /></div>}
                            value={keys.anthropic_api_key}
                            onChange={v => setKeys({ ...keys, anthropic_api_key: v })}
                            placeholder="sk-ant-..."
                        />
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <FeatureStatus
                            icon={<Zap className="h-4 w-4 text-amber-500" />}
                            title="고성능 VLM 엔진"
                            description="이미지 자동 태깅 및 상세 페이지 분석"
                        />
                        <FeatureStatus
                            icon={<Eye className="h-4 w-4 text-blue-500" />}
                            title="지능형 SEO 최적화"
                            description="마켓 플랫폼별 노출 키워드 자동 생성"
                        />
                    </div>
                </CardContent>
                <CardFooter className="bg-muted/5 border-t border-border/50 p-6 flex justify-center">
                    <Button
                        size="lg"
                        className="h-12 rounded-2xl font-black px-16 shadow-xl shadow-violet-500/20 transition-all hover:scale-105 active:scale-95 bg-violet-600 hover:bg-violet-700"
                        onClick={() => onSave(keys)}
                        disabled={isLoading}
                    >
                        {isLoading ? "저장 중..." : "AI API 키 설정 저장 및 적용"}
                    </Button>
                </CardFooter>
            </Card>

            <div className="p-4 rounded-2xl border border-violet-500/20 bg-violet-500/5 flex items-start gap-3">
                <InfoIcon className="h-4 w-4 text-violet-500 mt-0.5" />
                <p className="text-[10px] text-violet-800/70 leading-relaxed font-bold">
                    입력하신 API 키는 데이터베이스에 암호화되어 저장되며, 상품 가공 및 이미지 분석 시에만 사용됩니다. <br />
                    OpenAI 혹은 Gemini 키 중 하나만 설정되어 있어도 가공 기능이 작동합니다.
                </p>
            </div>
        </div>
    );
}

function AIProviderCard({ name, description, icon, value, onChange, placeholder }: { name: string, description: string, icon: React.ReactNode, value: string, onChange: (v: string) => void, placeholder: string }) {
    return (
        <div className="space-y-4 p-6 rounded-3xl border border-border/40 bg-muted/5 transition-all hover:bg-muted/10">
            <div className="flex items-center gap-4">
                {icon}
                <div className="flex flex-col">
                    <span className="text-xs font-black text-foreground">{name}</span>
                    <span className="text-[10px] text-muted-foreground font-medium">{description}</span>
                </div>
            </div>
            <div className="relative group">
                <Key className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/30 group-focus-within:text-primary transition-colors" />
                <Input
                    type="password"
                    value={value}
                    onChange={e => onChange(e.target.value)}
                    placeholder={placeholder}
                    className="pl-10 h-10 bg-background border-border/50 rounded-xl font-mono text-xs focus:ring-1"
                />
            </div>
        </div>
    );
}

function FeatureStatus({ icon, title, description }: { icon: React.ReactNode, title: string, description: string }) {
    return (
        <div className="flex items-center gap-4 p-4 rounded-2xl border border-border/30 bg-muted/5">
            <div className="h-10 w-10 flex items-center justify-center rounded-full bg-background shadow-sm border border-border/30">
                {icon}
            </div>
            <div className="flex flex-col">
                <span className="text-[11px] font-black text-foreground">{title}</span>
                <span className="text-[10px] text-muted-foreground">{description}</span>
            </div>
        </div>
    );
}

function InfoIcon(props: React.SVGProps<SVGSVGElement>) {
    return (
        <svg
            {...props}
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <circle cx="12" cy="12" r="10" />
            <path d="M12 16v-4" />
            <path d="M12 8h.01" />
        </svg>
    );
}
