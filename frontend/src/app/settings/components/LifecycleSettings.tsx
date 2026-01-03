"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import {
    Settings,
    Save,
    Search,
    Upload,
    Download,
    Plus,
    Trash2,
    AlertCircle,
    ArrowUpDown,
    CheckCircle2,
    TrendingUp,
    Calendar,
    ChevronRight
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { toInt, toFloat, collectCategoryRowErrors, getSortedRows, buildCategoryRowsFromCsv, buildCategoryAdjustedFromRows } from "../utils";
import { cn } from "@/lib/utils";

interface LifecycleCriteria {
    step1_to_step2: {
        min_sales: number;
        min_ctr: number;
        min_views: number;
        min_days_listed: number;
    };
    step2_to_step3: {
        min_sales: number;
        min_repeat_purchase: number;
        min_customer_retention: number;
        min_revenue: number;
        min_days_in_step2: number;
    };
}

interface LifecycleSettingsProps {
    initialData?: LifecycleCriteria;
    initialCategoryRows?: Array<Record<string, string>>;
    onSave: (criteria: LifecycleCriteria, categoryAdjusted: Record<string, any>) => Promise<void>;
    isLoading?: boolean;
}

export default function LifecycleSettings({ initialData, initialCategoryRows, onSave, isLoading }: LifecycleSettingsProps) {
    const [criteria, setCriteria] = useState<LifecycleCriteria>(initialData || {
        step1_to_step2: { min_sales: 1, min_ctr: 0.02, min_views: 100, min_days_listed: 7 },
        step2_to_step3: { min_sales: 5, min_repeat_purchase: 1, min_customer_retention: 0.1, min_revenue: 100000, min_days_in_step2: 14 }
    });
    const [categoryRows, setCategoryRows] = useState<Array<Record<string, string>>>(initialCategoryRows || []);
    const [searchTerm, setSearchTerm] = useState("");
    const [sortConfig, setSortConfig] = useState<{ key: string, direction: 'asc' | 'desc' }>({ key: 'name', direction: 'asc' });
    const csvInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (initialData) setCriteria(initialData);
        if (initialCategoryRows) setCategoryRows(initialCategoryRows);
    }, [initialData, initialCategoryRows]);

    const rowValidation = useMemo(() => collectCategoryRowErrors(categoryRows), [categoryRows]);

    const filteredAndSortedRows = useMemo(() => {
        let rows = categoryRows.filter(row =>
            row.name.toLowerCase().includes(searchTerm.toLowerCase())
        );
        return getSortedRows(rows, sortConfig.key, sortConfig.direction);
    }, [categoryRows, searchTerm, sortConfig]);

    const handleSort = (key: string) => {
        setSortConfig(prev => ({
            key,
            direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
        }));
    };

    const handleAddRow = () => {
        setCategoryRows([{
            name: "",
            min_sales: "",
            min_ctr: "",
            min_views: "",
            min_days_listed: "",
            min_repeat_purchase: "",
            min_customer_retention: "",
            min_revenue: "",
            min_days_in_step2: ""
        }, ...categoryRows]);
    };

    const handleRemoveRow = (index: number) => {
        setCategoryRows(categoryRows.filter((_, i) => i !== index));
    };

    const handleUpdateRow = (index: number, field: string, value: string) => {
        const newRows = [...categoryRows];
        newRows[index] = { ...newRows[index], [field]: value };
        setCategoryRows(newRows);
    };

    const handleImportCsv = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (event) => {
            const text = event.target?.result as string;
            const newRows = buildCategoryRowsFromCsv(text);
            if (newRows.length > 0) {
                setCategoryRows([...newRows, ...categoryRows]);
                alert(`${newRows.length}개의 카테고리 설정을 불러왔습니다.`);
            }
        };
        reader.readAsText(file);
    };

    const handleExportCsv = () => {
        const headers = ["name", "min_sales", "min_ctr", "min_views", "min_days_listed", "min_repeat_purchase", "min_customer_retention", "min_revenue", "min_days_in_step2"];
        const csvContent = [
            headers.join(","),
            ...categoryRows.map(row => headers.map(h => row[h] || "").join(","))
        ].join("\n");
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.setAttribute("href", url);
        link.setAttribute("download", "category_lifecycle_criteria.csv");
        link.click();
    };

    const handleSave = () => {
        const categoryAdjusted = buildCategoryAdjustedFromRows(categoryRows);
        onSave(criteria, categoryAdjusted);
    };

    return (
        <div className="space-y-6">
            {/* Global Crtiteria */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Card className="border border-border/50 bg-card/50 backdrop-blur-sm overflow-hidden">
                    <CardHeader className="bg-muted/5 border-b border-border/50">
                        <CardTitle className="text-sm font-black flex items-center gap-2">
                            <div className="h-6 w-6 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                                <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />
                            </div>
                            STEP 1 → 2 (검증기 진입)
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="p-6 space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <InputField label="최소 판매량" value={criteria.step1_to_step2.min_sales} onChange={v => setCriteria({ ...criteria, step1_to_step2: { ...criteria.step1_to_step2, min_sales: toInt(v, 0) } })} />
                            <InputField label="최소 CTR (%)" value={criteria.step1_to_step2.min_ctr * 100} onChange={v => setCriteria({ ...criteria, step1_to_step2: { ...criteria.step1_to_step2, min_ctr: toFloat(v, 0) / 100 } })} step="0.1" />
                            <InputField label="최소 노출수" value={criteria.step1_to_step2.min_views} onChange={v => setCriteria({ ...criteria, step1_to_step2: { ...criteria.step1_to_step2, min_views: toInt(v, 0) } })} />
                            <InputField label="최소 등록일" value={criteria.step1_to_step2.min_days_listed} onChange={v => setCriteria({ ...criteria, step1_to_step2: { ...criteria.step1_to_step2, min_days_listed: toInt(v, 0) } })} suffix="일" />
                        </div>
                    </CardContent>
                </Card>

                <Card className="border border-border/50 bg-card/50 backdrop-blur-sm overflow-hidden">
                    <CardHeader className="bg-muted/5 border-b border-border/50">
                        <CardTitle className="text-sm font-black flex items-center gap-2">
                            <div className="h-6 w-6 rounded-lg bg-blue-500/10 flex items-center justify-center">
                                <CheckCircle2 className="h-3.5 w-3.5 text-blue-500" />
                            </div>
                            STEP 2 → 3 (스테디셀러 승격)
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="p-6 space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <InputField label="최소 판매량" value={criteria.step2_to_step3.min_sales} onChange={v => setCriteria({ ...criteria, step2_to_step3: { ...criteria.step2_to_step3, min_sales: toInt(v, 0) } })} />
                            <InputField label="최소 재구매" value={criteria.step2_to_step3.min_repeat_purchase} onChange={v => setCriteria({ ...criteria, step2_to_step3: { ...criteria.step2_to_step3, min_repeat_purchase: toInt(v, 0) } })} />
                            <InputField label="유지율 (%)" value={criteria.step2_to_step3.min_customer_retention * 100} onChange={v => setCriteria({ ...criteria, step2_to_step3: { ...criteria.step2_to_step3, min_customer_retention: toFloat(v, 0) / 100 } })} step="0.1" />
                            <InputField label="최소 매출" value={criteria.step2_to_step3.min_revenue} onChange={v => setCriteria({ ...criteria, step2_to_step3: { ...criteria.step2_to_step3, min_revenue: toInt(v, 0) } })} suffix="원" />
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Category Overrides */}
            <Card className="border border-border/50 bg-card/50 backdrop-blur-sm">
                <CardHeader className="flex flex-row items-center justify-between pb-4">
                    <CardTitle className="text-sm font-black flex items-center gap-2">
                        <Settings className="h-4 w-4 text-primary" />
                        카테고리별 보정 기준 (Category Overrides)
                    </CardTitle>
                    <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm" onClick={() => csvInputRef.current?.click()} className="h-9 rounded-xl font-bold bg-background/50">
                            <Upload className="mr-2 h-3.5 w-3.5" />
                            CSV 가져오기
                        </Button>
                        <Button variant="outline" size="sm" onClick={handleExportCsv} className="h-9 rounded-xl font-bold bg-background/50">
                            <Download className="mr-2 h-3.5 w-3.5" />
                            내보내기
                        </Button>
                        <Button size="sm" onClick={handleAddRow} className="h-9 rounded-xl font-black px-4">
                            <Plus className="mr-2 h-3.5 w-3.5" />
                            카테고리 추가
                        </Button>
                        <input type="file" ref={csvInputRef} onChange={handleImportCsv} className="hidden" accept=".csv" />
                    </div>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="relative group">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
                        <Input
                            placeholder="카테고리 검색..."
                            value={searchTerm}
                            onChange={e => setSearchTerm(e.target.value)}
                            className="pl-10 h-11 bg-muted/20 border-border/50 rounded-2xl"
                        />
                    </div>

                    <div className="rounded-2xl border border-border/50 overflow-hidden bg-background/50">
                        <div className="overflow-x-auto">
                            <table className="w-full text-[11px] text-left border-collapse">
                                <thead>
                                    <tr className="bg-muted/30 border-b border-border/50">
                                        <th className="p-3 font-black text-foreground/70 uppercase tracking-widest cursor-pointer hover:bg-muted/50 transition-colors" onClick={() => handleSort('name')}>
                                            <div className="flex items-center gap-2">
                                                카테고리명 <ArrowUpDown className="h-3 w-3" />
                                            </div>
                                        </th>
                                        <th className="p-3 font-bold text-center">판매(S1)</th>
                                        <th className="p-3 font-bold text-center">CTR(S1)</th>
                                        <th className="p-3 font-bold text-center">판매(S2)</th>
                                        <th className="p-3 font-bold text-center">매출(S2)</th>
                                        <th className="p-3 font-bold text-center w-[60px]">관리</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredAndSortedRows.map((row, idx) => (
                                        <tr key={idx} className="border-b border-border/30 hover:bg-muted/10 transition-colors group">
                                            <td className="p-2">
                                                <Input
                                                    value={row.name}
                                                    onChange={e => handleUpdateRow(idx, 'name', e.target.value)}
                                                    className={cn("h-8 bg-transparent border-none focus-visible:ring-1", rowValidation.fieldErrors[idx]?.name && "bg-destructive/5")}
                                                />
                                            </td>
                                            <td className="p-2">
                                                <Input
                                                    type="number"
                                                    value={row.min_sales}
                                                    onChange={e => handleUpdateRow(idx, 'min_sales', e.target.value)}
                                                    className="h-8 bg-muted/30 text-center"
                                                />
                                            </td>
                                            <td className="p-2">
                                                <Input
                                                    type="number"
                                                    value={row.min_ctr}
                                                    onChange={e => handleUpdateRow(idx, 'min_ctr', e.target.value)}
                                                    className="h-8 bg-muted/30 text-center"
                                                />
                                            </td>
                                            <td className="p-2">
                                                <Input
                                                    type="number"
                                                    value={row.min_sales_s2 || row.min_sales}
                                                    onChange={e => handleUpdateRow(idx, 'min_sales_s2', e.target.value)}
                                                    className="h-8 bg-muted/30 text-center"
                                                />
                                            </td>
                                            <td className="p-2">
                                                <Input
                                                    type="number"
                                                    value={row.min_revenue}
                                                    onChange={e => handleUpdateRow(idx, 'min_revenue', e.target.value)}
                                                    className="h-8 bg-muted/30 text-center"
                                                />
                                            </td>
                                            <td className="p-2 text-center">
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-7 w-7 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-all"
                                                    onClick={() => handleRemoveRow(idx)}
                                                >
                                                    <Trash2 className="h-3.5 w-3.5" />
                                                </Button>
                                            </td>
                                        </tr>
                                    ))}
                                    {filteredAndSortedRows.length === 0 && (
                                        <tr>
                                            <td colSpan={6} className="p-10 text-center text-muted-foreground font-medium">
                                                검색 결과가 없습니다.
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </CardContent>
                <CardFooter className="bg-muted/5 border-t border-border/50 py-4 flex justify-between items-center px-6">
                    <p className="text-[10px] text-muted-foreground italic">
                        * 카테고리별 보정 기준이 없는 경우 상단의 전역 기준이 적용됩니다.
                    </p>
                    <Button
                        size="lg"
                        className="h-11 rounded-xl font-black px-12 shadow-lg shadow-primary/20"
                        onClick={handleSave}
                        disabled={isLoading || rowValidation.errors.length > 0}
                    >
                        {isLoading ? (
                            <div className="flex items-center gap-2">
                                <div className="h-4 w-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                                저장 중...
                            </div>
                        ) : (
                            <><Save className="mr-2 h-4 w-4" /> 라이프사이클 정책 업데이트</>
                        )}
                    </Button>
                </CardFooter>
            </Card>
        </div>
    );
}

function InputField({ label, value, onChange, step, suffix }: { label: string, value: any, onChange: (v: string) => void, step?: string, suffix?: string }) {
    return (
        <div className="space-y-1.5">
            <label className="text-[11px] font-bold text-muted-foreground ml-1">{label}</label>
            <div className="relative group">
                <Input
                    type="number"
                    step={step}
                    value={value}
                    onChange={e => onChange(e.target.value)}
                    className="h-10 font-mono font-black text-primary text-sm pr-10 focus:ring-1"
                />
                {suffix && (
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-black text-muted-foreground/50">
                        {suffix}
                    </span>
                )}
            </div>
        </div>
    );
}
