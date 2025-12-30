"use client";

import { useEffect, useRef, useState } from "react";
import { Settings, Save, AlertTriangle, Lock, Plus, RefreshCw, KeyRound } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { Badge } from "@/components/ui/Badge";
import { Select } from "@/components/ui/Select";
import { Table } from "@/components/ui/Table";

type SettingsTab = "orchestration" | "lifecycle" | "market" | "supplier" | "ai";

export default function SettingsPage() {
    const [activeTab, setActiveTab] = useState<SettingsTab>("orchestration");
    const [isLoading, setIsLoading] = useState(false);
    const [isLoadingSettings, setIsLoadingSettings] = useState(false);
    const [notification, setNotification] = useState<{ type: "success" | "error" | null; message: string }>({ type: null, message: "" });

    const defaultLifecycleCriteria = {
        step1_to_step2: {
            min_sales: 1,
            min_ctr: 0.02,
            min_views: 100,
            min_days_listed: 7,
        },
        step2_to_step3: {
            min_sales: 5,
            min_repeat_purchase: 1,
            min_customer_retention: 0.1,
            min_revenue: 100000,
            min_days_in_step2: 14,
        },
        category_adjusted: {
            "패션의류": { min_sales: 3 },
            "가전제품": { min_sales: 7 },
            "기본": {}
        }
    };

    const [orchestratorForm, setOrchestratorForm] = useState({
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
    });
    const [lifecycleCriteriaForm, setLifecycleCriteriaForm] = useState({
        step1_to_step2: { ...defaultLifecycleCriteria.step1_to_step2 },
        step2_to_step3: { ...defaultLifecycleCriteria.step2_to_step3 },
        category_adjusted_raw: JSON.stringify(defaultLifecycleCriteria.category_adjusted, null, 2)
    });
    const [categoryOverrideDraft, setCategoryOverrideDraft] = useState({
        name: "",
        min_sales: "",
        min_ctr: "",
        min_views: "",
        min_days_listed: "",
        min_repeat_purchase: "",
        min_customer_retention: "",
        min_revenue: "",
        min_days_in_step2: ""
    });
    const [categoryRows, setCategoryRows] = useState<Array<Record<string, string>>>([]);
    const [lastSavedCategoryRows, setLastSavedCategoryRows] = useState<Array<Record<string, string>>>([]);
    const [categorySort, setCategorySort] = useState<{ key: string; direction: "asc" | "desc" }>({
        key: "name",
        direction: "asc"
    });
    const [categoryFilter, setCategoryFilter] = useState("");
    const [autoSortEnabled, setAutoSortEnabled] = useState(false);
    const [highlightRowIndex, setHighlightRowIndex] = useState<number | null>(null);
    const csvInputRef = useRef<HTMLInputElement | null>(null);
    const [csvImportMode, setCsvImportMode] = useState<"merge" | "replace">("merge");
    const [pendingCsvRows, setPendingCsvRows] = useState<Array<Record<string, string>> | null>(null);
    const [pendingCsvMode, setPendingCsvMode] = useState<"merge" | "replace">("merge");
    const [lifecycleUiLoaded, setLifecycleUiLoaded] = useState(false);
    const [marketLoading, setMarketLoading] = useState(false);
    const [supplierLoading, setSupplierLoading] = useState(false);
    const [aiLoading, setAiLoading] = useState(false);
    const [coupangAccounts, setCoupangAccounts] = useState<any[]>([]);
    const [smartstoreAccounts, setSmartstoreAccounts] = useState<any[]>([]);
    const [ownerclanAccounts, setOwnerclanAccounts] = useState<any[]>([]);
    const [ownerclanPrimary, setOwnerclanPrimary] = useState<any | null>(null);
    const [syncJobs, setSyncJobs] = useState<any[]>([]);
    const [aiKeys, setAiKeys] = useState<any[]>([]);
    const [coupangForm, setCoupangForm] = useState({
        name: "",
        vendor_id: "",
        vendor_user_id: "",
        access_key: "",
        secret_key: "",
        is_active: true
    });
    const [coupangEditId, setCoupangEditId] = useState<string | null>(null);
    const [smartstoreForm, setSmartstoreForm] = useState({
        name: "",
        client_id: "",
        client_secret: "",
        is_active: true
    });
    const [smartstoreEditId, setSmartstoreEditId] = useState<string | null>(null);
    const [ownerclanForm, setOwnerclanForm] = useState({
        user_type: "seller",
        username: "",
        password: "",
        set_primary: true,
        is_active: true
    });
    const [ownerclanSubmitting, setOwnerclanSubmitting] = useState(false);
    const [aiForm, setAiForm] = useState({
        provider: "openai",
        key: "",
        is_active: true
    });
    const [isSavingLifecycle, setIsSavingLifecycle] = useState(false);
    const toInt = (value: string, fallback: number) => {
        const parsed = parseInt(value, 10);
        return Number.isNaN(parsed) ? fallback : parsed;
    };
    const toFloat = (value: string, fallback: number) => {
        const parsed = parseFloat(value);
        return Number.isNaN(parsed) ? fallback : parsed;
    };
    const parseCategoryAdjusted = (raw: string) => {
        if (!raw.trim()) {
            return {};
        }
        try {
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== "object") {
                return null;
            }
            return parsed as Record<string, Record<string, unknown>>;
        } catch {
            return null;
        }
    };
    const parseNumberField = (value: string, isFloat = false) => {
        if (!value.trim()) {
            return null;
        }
        const parsed = isFloat ? parseFloat(value) : parseInt(value, 10);
        return Number.isNaN(parsed) ? null : parsed;
    };
    const buildCategoryAdjustedFromRows = (rows: Array<Record<string, string>>) => (
        rows.reduce<Record<string, Record<string, number>>>((acc, row) => {
            const name = row.name.trim();
            if (!name) {
                return acc;
            }
            const fields = [
                { key: "min_sales", isFloat: false },
                { key: "min_ctr", isFloat: true },
                { key: "min_views", isFloat: false },
                { key: "min_days_listed", isFloat: false },
                { key: "min_repeat_purchase", isFloat: false },
                { key: "min_customer_retention", isFloat: true },
                { key: "min_revenue", isFloat: false },
                { key: "min_days_in_step2", isFloat: false }
            ];
            const rules: Record<string, number> = {};
            fields.forEach(({ key, isFloat }) => {
                const value = parseNumberField(row[key] || "", isFloat);
                if (value !== null) {
                    rules[key] = value;
                }
            });
            if (Object.keys(rules).length > 0) {
                acc[name] = rules;
            }
            return acc;
        }, {})
    );
    const parseCsvLine = (line: string) => {
        const result: string[] = [];
        let current = "";
        let inQuotes = false;
        for (let i = 0; i < line.length; i += 1) {
            const char = line[i];
            if (char === "\"") {
                if (inQuotes && line[i + 1] === "\"") {
                    current += "\"";
                    i += 1;
                } else {
                    inQuotes = !inQuotes;
                }
                continue;
            }
            if (char === "," && !inQuotes) {
                result.push(current);
                current = "";
                continue;
            }
            current += char;
        }
        result.push(current);
        return result.map((value) => value.trim());
    };
    const buildCategoryRowsFromCsv = (csvText: string) => {
        const rawLines = csvText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
        if (rawLines.length === 0) {
            return [];
        }
        const headerIndex = rawLines.findIndex((line) => {
            const cells = parseCsvLine(line);
            return cells.length > 0 && !cells[0].startsWith("#");
        });
        if (headerIndex < 0) {
            return [];
        }
        const header = parseCsvLine(rawLines[headerIndex]).map((value) => value.toLowerCase());
        const keyMap: Record<string, string> = {
            category: "name",
            name: "name",
            min_sales: "min_sales",
            min_ctr: "min_ctr",
            min_views: "min_views",
            min_days_listed: "min_days_listed",
            min_repeat_purchase: "min_repeat_purchase",
            min_customer_retention: "min_customer_retention",
            min_revenue: "min_revenue",
            min_days_in_step2: "min_days_in_step2"
        };
        const indexes = header.map((label) => keyMap[label]).filter(Boolean);
        return rawLines.slice(headerIndex + 1).map((line) => {
            const values = parseCsvLine(line);
            if (values[0]?.startsWith("#")) {
                return null;
            }
            const row: Record<string, string> = {
                name: "",
                min_sales: "",
                min_ctr: "",
                min_views: "",
                min_days_listed: "",
                min_repeat_purchase: "",
                min_customer_retention: "",
                min_revenue: "",
                min_days_in_step2: ""
            };
            indexes.forEach((key, idx) => {
                row[key] = values[idx] ?? "";
            });
            return row;
        }).filter((row): row is Record<string, string> => Boolean(row && row.name.trim()));
    };
    const getCategoryRowMap = (rows: Array<Record<string, string>>) => (
        rows.reduce<Record<string, Record<string, string>>>((acc, row) => {
            const name = row.name.trim();
            if (name) {
                acc[name] = row;
            }
            return acc;
        }, {})
    );
    const computeCategoryDiff = (
        currentRows: Array<Record<string, string>>,
        baselineRows: Array<Record<string, string>>
    ) => {
        const keys = [
            "min_sales",
            "min_ctr",
            "min_views",
            "min_days_listed",
            "min_repeat_purchase",
            "min_customer_retention",
            "min_revenue",
            "min_days_in_step2"
        ];
        const current = getCategoryRowMap(currentRows);
        const baseline = getCategoryRowMap(baselineRows);
        const added: string[] = [];
        const removed: string[] = [];
        const changed: string[] = [];

        Object.keys(current).forEach((name) => {
            if (!baseline[name]) {
                added.push(name);
                return;
            }
            const currentRow = current[name];
            const baselineRow = baseline[name];
            const isChanged = keys.some((key) => (currentRow[key] || "") !== (baselineRow[key] || ""));
            if (isChanged) {
                changed.push(name);
            }
        });
        Object.keys(baseline).forEach((name) => {
            if (!current[name]) {
                removed.push(name);
            }
        });
        return { added, removed, changed };
    };
    const renderDiffLine = (label: string, items: string[], onClickItem?: (name: string) => void) => {
        if (items.length === 0) {
            return null;
        }
        return (
            <div className="text-[9px] text-muted-foreground">
                {label}:{" "}
                {items.slice(0, 5).map((name, index) => (
                    <button
                        key={`${label}-${name}-${index}`}
                        type="button"
                        className={`underline-offset-2 ${onClickItem ? "underline text-primary hover:text-primary/80" : ""}`}
                        onClick={() => onClickItem?.(name)}
                    >
                        {name}{index < Math.min(items.length, 5) - 1 ? ", " : ""}
                    </button>
                ))}
                {items.length > 5 ? ` 외 ${items.length - 5}건` : ""}
            </div>
        );
    };
    const getSortedRows = (rows: Array<Record<string, string>>, key: string, direction: "asc" | "desc") => {
        const numericKeys = new Set([
            "min_sales",
            "min_ctr",
            "min_views",
            "min_days_listed",
            "min_repeat_purchase",
            "min_customer_retention",
            "min_revenue",
            "min_days_in_step2"
        ]);
        const next = [...rows];
        next.sort((a, b) => {
            const aVal = a[key] || "";
            const bVal = b[key] || "";
            if (numericKeys.has(key)) {
                const aNum = parseFloat(aVal);
                const bNum = parseFloat(bVal);
                const aValid = Number.isFinite(aNum);
                const bValid = Number.isFinite(bNum);
                if (!aValid && !bValid) {
                    return 0;
                }
                if (!aValid) {
                    return direction === "asc" ? 1 : -1;
                }
                if (!bValid) {
                    return direction === "asc" ? -1 : 1;
                }
                return direction === "asc" ? aNum - bNum : bNum - aNum;
            }
            const comparison = aVal.localeCompare(bVal);
            return direction === "asc" ? comparison : -comparison;
        });
        return next;
    };
    const sortCategoryRows = (key: string, direction: "asc" | "desc") => {
        setCategoryRows((prev) => getSortedRows(prev, key, direction));
    };
    const collectCategoryRowErrors = (rows: Array<Record<string, string>>) => {
        const errors: string[] = [];
        const rowErrors: Record<number, string[]> = {};
        const fieldErrors: Record<number, Record<string, string>> = {};
        const seen = new Set<string>();
        rows.forEach((row, index) => {
            const pushRowError = (message: string) => {
                errors.push(message);
                rowErrors[index] = rowErrors[index] || [];
                rowErrors[index].push(message);
            };
            const pushFieldError = (field: string, message: string) => {
                fieldErrors[index] = fieldErrors[index] || {};
                if (!fieldErrors[index][field]) {
                    fieldErrors[index][field] = message;
                }
            };
            const name = row.name.trim();
            if (!name) {
                const message = `카테고리명이 비어 있습니다 (행 ${index + 1})`;
                pushRowError(message);
                pushFieldError("name", message);
            } else if (seen.has(name)) {
                const message = `중복된 카테고리명입니다: ${name}`;
                pushRowError(message);
                pushFieldError("name", message);
            } else {
                seen.add(name);
            }
            const fields = [
                { key: "min_sales", isFloat: false },
                { key: "min_ctr", isFloat: true, min: 0, max: 1 },
                { key: "min_views", isFloat: false },
                { key: "min_days_listed", isFloat: false },
                { key: "min_repeat_purchase", isFloat: false },
                { key: "min_customer_retention", isFloat: true, min: 0, max: 1 },
                { key: "min_revenue", isFloat: false },
                { key: "min_days_in_step2", isFloat: false }
            ];
            fields.forEach(({ key, isFloat, min, max }) => {
                const raw = row[key] || "";
                if (!raw.trim()) {
                    return;
                }
                const value = parseNumberField(raw, isFloat);
                const label = name || `행 ${index + 1}`;
                if (value === null) {
                    const message = `${label}: ${key} 숫자 형식이 올바르지 않습니다.`;
                    pushRowError(message);
                    pushFieldError(key, message);
                    return;
                }
                if (value < 0) {
                    const message = `${label}: ${key}는 0 이상이어야 합니다.`;
                    pushRowError(message);
                    pushFieldError(key, message);
                    return;
                }
                if (min !== undefined && value < min) {
                    const message = `${label}: ${key}는 ${min} 이상이어야 합니다.`;
                    pushRowError(message);
                    pushFieldError(key, message);
                }
                if (max !== undefined && value > max) {
                    const message = `${label}: ${key}는 ${max} 이하여야 합니다.`;
                    pushRowError(message);
                    pushFieldError(key, message);
                }
            });
        });
        return { errors, rowErrors, fieldErrors };
    };

    useEffect(() => {
        let active = true;
        const loadSettings = async () => {
            setIsLoadingSettings(true);
            try {
                const [orchestratorResult, lifecycleResult] = await Promise.allSettled([
                    fetch("/api/settings/orchestrator"),
                    fetch("/api/settings/lifecycle-criteria"),
                ]);

                if (orchestratorResult.status === "fulfilled") {
                    const response = orchestratorResult.value;
                    if (response.ok) {
                        const data = await response.json();
                        if (active) {
                            setOrchestratorForm((prev) => ({ ...prev, ...data }));
                        }
                    } else {
                        throw new Error("Failed to load orchestrator settings");
                    }
                }

                if (lifecycleResult.status === "fulfilled") {
                    const response = lifecycleResult.value;
                    if (response.ok) {
                        const data = await response.json();
                        if (active) {
                            setLifecycleCriteriaForm({
                                step1_to_step2: { ...defaultLifecycleCriteria.step1_to_step2, ...(data?.step1_to_step2 || {}) },
                                step2_to_step3: { ...defaultLifecycleCriteria.step2_to_step3, ...(data?.step2_to_step3 || {}) },
                                category_adjusted_raw: JSON.stringify(data?.category_adjusted || defaultLifecycleCriteria.category_adjusted, null, 2)
                            });
                            const parsed = data?.category_adjusted || defaultLifecycleCriteria.category_adjusted;
                            if (parsed && typeof parsed === "object") {
                                const rows = Object.entries(parsed).map(([name, rules]) => ({
                                    name,
                                    min_sales: rules?.min_sales?.toString?.() || "",
                                    min_ctr: rules?.min_ctr?.toString?.() || "",
                                    min_views: rules?.min_views?.toString?.() || "",
                                    min_days_listed: rules?.min_days_listed?.toString?.() || "",
                                    min_repeat_purchase: rules?.min_repeat_purchase?.toString?.() || "",
                                    min_customer_retention: rules?.min_customer_retention?.toString?.() || "",
                                    min_revenue: rules?.min_revenue?.toString?.() || "",
                                    min_days_in_step2: rules?.min_days_in_step2?.toString?.() || ""
                                }));
                                setCategoryRows(rows);
                                setLastSavedCategoryRows(rows);
                            }
                        }
                    } else {
                        throw new Error("Failed to load lifecycle criteria");
                    }
                }
            } catch (error) {
                console.error("Failed to load orchestrator settings", error);
                if (active && typeof window !== "undefined") {
                    const draft = window.localStorage.getItem("lifecycleCriteriaDraft");
                    if (draft) {
                        try {
                            const parsed = JSON.parse(draft);
                            setLifecycleCriteriaForm({
                                step1_to_step2: { ...defaultLifecycleCriteria.step1_to_step2, ...(parsed?.step1_to_step2 || {}) },
                                step2_to_step3: { ...defaultLifecycleCriteria.step2_to_step3, ...(parsed?.step2_to_step3 || {}) },
                                category_adjusted_raw: JSON.stringify(parsed?.category_adjusted || defaultLifecycleCriteria.category_adjusted, null, 2)
                            });
                            const parsedCategory = parsed?.category_adjusted || {};
                            const rows = Object.entries(parsedCategory).map(([name, rules]) => ({
                                name,
                                min_sales: rules?.min_sales?.toString?.() || "",
                                min_ctr: rules?.min_ctr?.toString?.() || "",
                                min_views: rules?.min_views?.toString?.() || "",
                                min_days_listed: rules?.min_days_listed?.toString?.() || "",
                                min_repeat_purchase: rules?.min_repeat_purchase?.toString?.() || "",
                                min_customer_retention: rules?.min_customer_retention?.toString?.() || "",
                                min_revenue: rules?.min_revenue?.toString?.() || "",
                                min_days_in_step2: rules?.min_days_in_step2?.toString?.() || ""
                            }));
                            setCategoryRows(rows);
                        } catch (parseError) {
                            console.error("Failed to load lifecycle criteria draft", parseError);
                        }
                    }
                }
                if (active) {
                    setNotification({ type: "error", message: "설정을 불러오지 못했습니다." });
                }
            } finally {
                if (active) {
                    setIsLoadingSettings(false);
                }
            }
        };
        loadSettings();
        return () => {
            active = false;
        };
    }, []);
    const loadMarketAccounts = async () => {
        setMarketLoading(true);
        try {
            const [coupangRes, smartstoreRes] = await Promise.all([
                fetch("/api/settings/markets/coupang/accounts"),
                fetch("/api/settings/markets/smartstore/accounts"),
            ]);
            if (!coupangRes.ok || !smartstoreRes.ok) {
                throw new Error("Failed to load market accounts");
            }
            const [coupangData, smartstoreData] = await Promise.all([
                coupangRes.json(),
                smartstoreRes.json(),
            ]);
            setCoupangAccounts(coupangData || []);
            setSmartstoreAccounts(smartstoreData || []);
        } catch (error) {
            console.error("Failed to load market accounts", error);
            setNotification({ type: "error", message: "마켓 계정 정보를 불러오지 못했습니다." });
        } finally {
            setMarketLoading(false);
        }
    };

    const loadSupplierData = async () => {
        setSupplierLoading(true);
        try {
            const [primaryRes, accountsRes, jobsRes] = await Promise.all([
                fetch("/api/settings/suppliers/ownerclan/primary"),
                fetch("/api/settings/suppliers/ownerclan/accounts"),
                fetch("/api/suppliers/sync/jobs?supplierCode=ownerclan&limit=10"),
            ]);
            if (!primaryRes.ok || !accountsRes.ok || !jobsRes.ok) {
                throw new Error("Failed to load supplier data");
            }
            const primaryData = await primaryRes.json();
            const accountsData = await accountsRes.json();
            const jobsData = await jobsRes.json();
            setOwnerclanPrimary(primaryData?.account || null);
            setOwnerclanAccounts(accountsData || []);
            setSyncJobs(jobsData || []);
        } catch (error) {
            console.error("Failed to load supplier data", error);
            setNotification({ type: "error", message: "공급사 정보를 불러오지 못했습니다." });
        } finally {
            setSupplierLoading(false);
        }
    };

    const loadAIKeys = async () => {
        setAiLoading(true);
        try {
            const response = await fetch("/api/settings/ai/keys");
            if (!response.ok) {
                throw new Error("Failed to load AI keys");
            }
            const data = await response.json();
            setAiKeys(data || []);
        } catch (error) {
            console.error("Failed to load AI keys", error);
            setNotification({ type: "error", message: "AI 키 정보를 불러오지 못했습니다." });
        } finally {
            setAiLoading(false);
        }
    };

    useEffect(() => {
        if (activeTab === "market") {
            loadMarketAccounts();
        }
        if (activeTab === "supplier") {
            loadSupplierData();
        }
        if (activeTab === "ai") {
            loadAIKeys();
        }
    }, [activeTab]);
    useEffect(() => {
        let active = true;
        const loadLifecycleUiPreferences = async () => {
            try {
                const response = await fetch("/api/settings/lifecycle-ui");
                if (!response.ok) {
                    if (typeof window !== "undefined") {
                        const draft = window.localStorage.getItem("lifecycleUiDraft");
                        if (draft) {
                            const parsed = JSON.parse(draft);
                            if (parsed?.categorySort?.key && parsed?.categorySort?.direction) {
                                setCategorySort({ key: parsed.categorySort.key, direction: parsed.categorySort.direction });
                            }
                            if (typeof parsed?.autoSortEnabled === "boolean") {
                                setAutoSortEnabled(parsed.autoSortEnabled);
                            }
                            if (typeof parsed?.categoryFilter === "string") {
                                setCategoryFilter(parsed.categoryFilter);
                            }
                        }
                    }
                    return;
                }
                const data = await response.json();
                if (!active || !data) {
                    return;
                }
                if (data?.categorySort?.key && data?.categorySort?.direction) {
                    setCategorySort({ key: data.categorySort.key, direction: data.categorySort.direction });
                }
                if (typeof data?.autoSortEnabled === "boolean") {
                    setAutoSortEnabled(data.autoSortEnabled);
                }
                if (typeof data?.categoryFilter === "string") {
                    setCategoryFilter(data.categoryFilter);
                }
                setLifecycleUiLoaded(true);
            } catch (error) {
                console.error("Failed to load lifecycle UI preferences", error);
                if (typeof window !== "undefined") {
                    const draft = window.localStorage.getItem("lifecycleUiDraft");
                    if (draft) {
                        try {
                            const parsed = JSON.parse(draft);
                            if (parsed?.categorySort?.key && parsed?.categorySort?.direction) {
                                setCategorySort({ key: parsed.categorySort.key, direction: parsed.categorySort.direction });
                            }
                            if (typeof parsed?.autoSortEnabled === "boolean") {
                                setAutoSortEnabled(parsed.autoSortEnabled);
                            }
                            if (typeof parsed?.categoryFilter === "string") {
                                setCategoryFilter(parsed.categoryFilter);
                            }
                        } catch (parseError) {
                            console.error("Failed to load lifecycle UI draft", parseError);
                        }
                    }
                }
            }
        };
        loadLifecycleUiPreferences();
        return () => {
            active = false;
        };
    }, []);
    useEffect(() => {
        if (lifecycleUiLoaded || typeof window === "undefined") {
            return;
        }
        const saved = window.localStorage.getItem("lifecycleCategorySort");
        if (!saved) {
            return;
        }
        try {
            const parsed = JSON.parse(saved);
            if (parsed?.key && parsed?.direction) {
                setCategorySort({ key: parsed.key, direction: parsed.direction });
            }
            if (typeof parsed?.autoSortEnabled === "boolean") {
                setAutoSortEnabled(parsed.autoSortEnabled);
            }
            if (typeof parsed?.categoryFilter === "string") {
                setCategoryFilter(parsed.categoryFilter);
            }
        } catch {
            // ignore corrupted saved state
        }
    }, [lifecycleUiLoaded]);
    useEffect(() => {
        if (typeof window === "undefined") {
            return;
        }
        window.localStorage.setItem(
            "lifecycleCategorySort",
            JSON.stringify({ ...categorySort, autoSortEnabled, categoryFilter })
        );
    }, [categorySort, autoSortEnabled, categoryFilter]);
    useEffect(() => {
        saveLifecycleUiPreferences({ categorySort, autoSortEnabled, categoryFilter });
    }, [categorySort, autoSortEnabled, categoryFilter]);
    useEffect(() => {
        if (categoryRows.length === 0) {
            return;
        }
        const nextRaw = JSON.stringify(buildCategoryAdjustedFromRows(categoryRows), null, 2);
        setLifecycleCriteriaForm((prev) => (
            prev.category_adjusted_raw === nextRaw
                ? prev
                : { ...prev, category_adjusted_raw: nextRaw }
        ));
    }, [categoryRows]);

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
    const saveLifecycleUiPreferences = async (payload: { categorySort: { key: string; direction: "asc" | "desc" }; autoSortEnabled: boolean; categoryFilter: string; }) => {
        try {
            const response = await fetch("/api/settings/lifecycle-ui", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (!response.ok) {
                console.error("Failed to save lifecycle UI preferences");
                if (typeof window !== "undefined") {
                    window.localStorage.setItem("lifecycleUiDraft", JSON.stringify(payload));
                }
            }
        } catch (error) {
            console.error("Failed to save lifecycle UI preferences", error);
            if (typeof window !== "undefined") {
                window.localStorage.setItem("lifecycleUiDraft", JSON.stringify(payload));
            }
        }
    };

    const categoryRowValidation = collectCategoryRowErrors(categoryRows);
    const getFieldError = (rowIndex: number, field: string) => (
        categoryRowValidation.fieldErrors[rowIndex]?.[field]
    );
    const filteredCategoryRows = categoryRows
        .map((row, index) => ({ row, index }))
        .filter(({ row }) => {
            const query = categoryFilter.trim().toLowerCase();
            if (!query) {
                return true;
            }
            const combined = [row.name, ...Object.values(row)]
                .filter(Boolean)
                .join(" ")
                .toLowerCase();
            return combined.includes(query);
        });
    const query = categoryFilter.trim().toLowerCase();
    const getMatchClass = (value: string) => (
        query && value.toLowerCase().includes(query) ? "bg-primary/10" : ""
    );
    const scrollToCategory = (name: string) => {
        const index = categoryRows.findIndex((row) => row.name.trim() === name);
        if (index < 0) {
            return;
        }
        setCategoryFilter(name);
        const element = document.getElementById(`category-row-${index}`);
        if (element) {
            element.scrollIntoView({ behavior: "smooth", block: "center" });
            setHighlightRowIndex(index);
            window.setTimeout(() => setHighlightRowIndex(null), 2000);
        }
    };
    const handleDiffClick = (name: string) => {
        scrollToCategory(name);
        if (isSavingLifecycle || categoryRowValidation.errors.length > 0) {
            return;
        }
        saveLifecycleCriteria();
    };
    const saveLifecycleCriteria = async () => {
        setIsSavingLifecycle(true);
        let categoryAdjusted;
        try {
            if (categoryRows.length > 0) {
                if (categoryRowValidation.errors.length > 0) {
                    const preview = categoryRowValidation.errors.slice(0, 3).join(" / ");
                    const suffix = categoryRowValidation.errors.length > 3 ? ` 외 ${categoryRowValidation.errors.length - 3}건` : "";
                    setNotification({ type: "error", message: `카테고리 보정 오류: ${preview}${suffix}` });
                    setIsSavingLifecycle(false);
                    return;
                }
                categoryAdjusted = buildCategoryAdjustedFromRows(categoryRows);
            } else {
                categoryAdjusted = lifecycleCriteriaForm.category_adjusted_raw
                    ? JSON.parse(lifecycleCriteriaForm.category_adjusted_raw)
                    : {};
            }
        } catch (error) {
            setNotification({ type: "error", message: "카테고리 보정 JSON 형식이 올바르지 않습니다." });
            setIsSavingLifecycle(false);
            return;
        }

        try {
            const response = await fetch("/api/settings/lifecycle-criteria", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    step1_to_step2: lifecycleCriteriaForm.step1_to_step2,
                    step2_to_step3: lifecycleCriteriaForm.step2_to_step3,
                    category_adjusted: categoryAdjusted,
                })
            });

            if (response.ok) {
                const saved = await response.json();
                const savedCategory = saved?.category_adjusted || {};
                setLifecycleCriteriaForm((prev) => ({
                    ...prev,
                    category_adjusted_raw: JSON.stringify(savedCategory, null, 2)
                }));
                if (savedCategory && typeof savedCategory === "object") {
                    const rows = Object.entries(savedCategory).map(([name, rules]) => ({
                        name,
                        min_sales: rules?.min_sales?.toString?.() || "",
                        min_ctr: rules?.min_ctr?.toString?.() || "",
                        min_views: rules?.min_views?.toString?.() || "",
                        min_days_listed: rules?.min_days_listed?.toString?.() || "",
                        min_repeat_purchase: rules?.min_repeat_purchase?.toString?.() || "",
                        min_customer_retention: rules?.min_customer_retention?.toString?.() || "",
                        min_revenue: rules?.min_revenue?.toString?.() || "",
                        min_days_in_step2: rules?.min_days_in_step2?.toString?.() || ""
                    }));
                    setCategoryRows(rows);
                    setLastSavedCategoryRows(rows);
                }
                setNotification({ type: "success", message: "라이프사이클 기준이 저장되었습니다." });
            } else {
                if (typeof window !== "undefined") {
                    window.localStorage.setItem(
                        "lifecycleCriteriaDraft",
                        JSON.stringify({
                            step1_to_step2: lifecycleCriteriaForm.step1_to_step2,
                            step2_to_step3: lifecycleCriteriaForm.step2_to_step3,
                            category_adjusted: categoryAdjusted
                        })
                    );
                }
                setNotification({ type: "error", message: "라이프사이클 기준 저장에 실패했습니다. 로컬에 임시 저장했습니다." });
            }
        } catch (error) {
            console.error("Failed to save lifecycle criteria", error);
            if (typeof window !== "undefined") {
                window.localStorage.setItem(
                    "lifecycleCriteriaDraft",
                    JSON.stringify({
                        step1_to_step2: lifecycleCriteriaForm.step1_to_step2,
                        step2_to_step3: lifecycleCriteriaForm.step2_to_step3,
                        category_adjusted: categoryAdjusted
                    })
                );
            }
            setNotification({ type: "error", message: "라이프사이클 기준 저장에 실패했습니다. 로컬에 임시 저장했습니다." });
        } finally {
            setIsSavingLifecycle(false);
        }
    };

    const applyCategoryOverride = () => {
        const name = categoryOverrideDraft.name.trim();
        if (!name) {
            setNotification({ type: "error", message: "카테고리명을 입력해 주세요." });
            return;
        }
        const nextOverride: Record<string, number> = {};
        const fields = [
            { key: "min_sales", isFloat: false },
            { key: "min_ctr", isFloat: true },
            { key: "min_views", isFloat: false },
            { key: "min_days_listed", isFloat: false },
            { key: "min_repeat_purchase", isFloat: false },
            { key: "min_customer_retention", isFloat: true },
            { key: "min_revenue", isFloat: false },
            { key: "min_days_in_step2", isFloat: false }
        ];
        fields.forEach(({ key, isFloat }) => {
            const value = parseNumberField((categoryOverrideDraft as Record<string, string>)[key], isFloat);
            if (value !== null) {
                nextOverride[key] = value;
            }
        });
        if (Object.keys(nextOverride).length === 0) {
            setNotification({ type: "error", message: "적어도 하나의 기준 값을 입력해 주세요." });
            return;
        }
        setCategoryRows((prev) => {
            const existingIndex = prev.findIndex((row) => row.name === name);
            const nextRow = {
                name,
                min_sales: nextOverride.min_sales?.toString?.() || "",
                min_ctr: nextOverride.min_ctr?.toString?.() || "",
                min_views: nextOverride.min_views?.toString?.() || "",
                min_days_listed: nextOverride.min_days_listed?.toString?.() || "",
                min_repeat_purchase: nextOverride.min_repeat_purchase?.toString?.() || "",
                min_customer_retention: nextOverride.min_customer_retention?.toString?.() || "",
                min_revenue: nextOverride.min_revenue?.toString?.() || "",
                min_days_in_step2: nextOverride.min_days_in_step2?.toString?.() || ""
            };
            if (existingIndex >= 0) {
                const next = [...prev];
                next[existingIndex] = { ...next[existingIndex], ...nextRow };
                return autoSortEnabled ? getSortedRows(next, categorySort.key, categorySort.direction) : next;
            }
            const next = [...prev, nextRow];
            return autoSortEnabled ? getSortedRows(next, categorySort.key, categorySort.direction) : next;
        });
        setCategoryOverrideDraft({
            name: "",
            min_sales: "",
            min_ctr: "",
            min_views: "",
            min_days_listed: "",
            min_repeat_purchase: "",
            min_customer_retention: "",
            min_revenue: "",
            min_days_in_step2: ""
        });
    };

    const removeCategoryOverride = (rowIndex: number) => {
        setCategoryRows((prev) => prev.filter((_, idx) => idx !== rowIndex));
    };

    const duplicateCategoryRow = (rowIndex: number) => {
        setCategoryRows((prev) => {
            const target = prev[rowIndex];
            if (!target) {
                return prev;
            }
            const baseName = target.name.trim() || "카테고리";
            const nextName = `${baseName} (복제)`;
            const row = {
                ...target,
                name: nextName
            };
            const next = [...prev];
            next.splice(rowIndex + 1, 0, row);
            return autoSortEnabled ? getSortedRows(next, categorySort.key, categorySort.direction) : next;
        });
    };
    const categoryCsvHeaders = [
        "name",
        "min_sales",
        "min_ctr",
        "min_views",
        "min_days_listed",
        "min_repeat_purchase",
        "min_customer_retention",
        "min_revenue",
        "min_days_in_step2"
    ];
    const buildCsv = (rows: Array<Record<string, string>>) => {
        const dataRows = rows.map((row) => (
            categoryCsvHeaders.map((key) => `"${(row[key] || "").replace(/"/g, "\"\"")}"`).join(",")
        ));
        return [categoryCsvHeaders.join(","), ...dataRows].join("\n");
    };
    const downloadCsv = (filename: string, rows: Array<Record<string, string>>) => {
        const csv = buildCsv(rows);
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        link.click();
        URL.revokeObjectURL(url);
    };
    const exportCategoryCsv = () => {
        if (categoryRows.length === 0) {
            setNotification({ type: "error", message: "내보낼 카테고리 보정 데이터가 없습니다." });
            return;
        }
        downloadCsv("lifecycle_category_overrides.csv", categoryRows);
    };
    const exportCategoryCsvTemplate = () => {
        const commentRow = {
            name: "# name은 필수, min_ctr/min_customer_retention은 0~1 범위",
            min_sales: "",
            min_ctr: "",
            min_views: "",
            min_days_listed: "",
            min_repeat_purchase: "",
            min_customer_retention: "",
            min_revenue: "",
            min_days_in_step2: ""
        };
        downloadCsv("lifecycle_category_overrides_template.csv", [commentRow]);
    };
    const exportCategoryCsvSample = () => {
        downloadCsv("lifecycle_category_overrides_sample.csv", [
            {
                name: "패션의류",
                min_sales: "2",
                min_ctr: "0.03",
                min_views: "200",
                min_days_listed: "5",
                min_repeat_purchase: "",
                min_customer_retention: "",
                min_revenue: "",
                min_days_in_step2: ""
            },
            {
                name: "가전제품",
                min_sales: "6",
                min_ctr: "0.015",
                min_views: "120",
                min_days_listed: "10",
                min_repeat_purchase: "1",
                min_customer_retention: "0.1",
                min_revenue: "150000",
                min_days_in_step2: "21"
            }
        ]);
    };
    const mergeCategoryRows = (incoming: Array<Record<string, string>>) => {
        const map = new Map<string, Record<string, string>>();
        categoryRows.forEach((row) => {
            if (row.name.trim()) {
                map.set(row.name.trim(), row);
            }
        });
        incoming.forEach((row) => {
            if (row.name.trim()) {
                map.set(row.name.trim(), row);
            }
        });
        return Array.from(map.values());
    };
    const importCategoryCsv = async (file: File | null, mode: "merge" | "replace") => {
        if (!file) {
            return;
        }
        try {
            const text = await file.text();
            const rows = buildCategoryRowsFromCsv(text);
            if (rows.length === 0) {
                setNotification({ type: "error", message: "가져올 수 있는 데이터가 없습니다." });
                return;
            }
            setPendingCsvRows(rows);
            setPendingCsvMode(mode);
            setNotification({ type: "success", message: "CSV 미리보기를 준비했습니다. 적용 또는 취소를 선택하세요." });
        } catch (error) {
            console.error("CSV import failed", error);
            setNotification({ type: "error", message: "CSV 가져오기에 실패했습니다." });
        } finally {
            if (csvInputRef.current) {
                csvInputRef.current.value = "";
            }
        }
    };
    const applyCsvImport = () => {
        if (!pendingCsvRows || pendingCsvRows.length === 0) {
            return;
        }
        const pendingValidation = collectCategoryRowErrors(pendingCsvRows);
        if (pendingValidation.errors.length > 0) {
            const preview = pendingValidation.errors.slice(0, 3).join(" / ");
            const suffix = pendingValidation.errors.length > 3 ? ` 외 ${pendingValidation.errors.length - 3}건` : "";
            setNotification({ type: "error", message: `CSV 오류: ${preview}${suffix}` });
            return;
        }
        const nextRows = pendingCsvMode === "merge" ? mergeCategoryRows(pendingCsvRows) : pendingCsvRows;
        setCategoryRows(autoSortEnabled ? getSortedRows(nextRows, categorySort.key, categorySort.direction) : nextRows);
        setPendingCsvRows(null);
        setNotification({ type: "success", message: `CSV 데이터를 ${pendingCsvMode === "merge" ? "병합" : "덮어쓰기"}했습니다.` });
    };
    const cancelCsvImport = () => {
        setPendingCsvRows(null);
        setNotification({ type: "success", message: "CSV 가져오기를 취소했습니다." });
    };
    const updatePendingCsvRowField = (rowIndex: number, field: string, value: string) => {
        setPendingCsvRows((prev) => {
            if (!prev) {
                return prev;
            }
            return prev.map((row, index) => (
                index === rowIndex ? { ...row, [field]: value } : row
            ));
        });
    };
    const removePendingCsvRow = (rowIndex: number) => {
        setPendingCsvRows((prev) => {
            if (!prev) {
                return prev;
            }
            return prev.filter((_, index) => index !== rowIndex);
        });
    };
    const addPendingCsvRow = () => {
        setPendingCsvRows((prev) => ([
            ...(prev || []),
            {
                name: "",
                min_sales: "",
                min_ctr: "",
                min_views: "",
                min_days_listed: "",
                min_repeat_purchase: "",
                min_customer_retention: "",
                min_revenue: "",
                min_days_in_step2: ""
            }
        ]));
    };
    const moveCategoryRow = (rowIndex: number, direction: "up" | "down") => {
        setAutoSortEnabled(false);
        setCategoryRows((prev) => {
            const targetIndex = direction === "up" ? rowIndex - 1 : rowIndex + 1;
            if (targetIndex < 0 || targetIndex >= prev.length) {
                return prev;
            }
            const next = [...prev];
            const [row] = next.splice(rowIndex, 1);
            next.splice(targetIndex, 0, row);
            return next;
        });
    };

    const resetCoupangForm = () => {
        setCoupangForm({
            name: "",
            vendor_id: "",
            vendor_user_id: "",
            access_key: "",
            secret_key: "",
            is_active: true
        });
        setCoupangEditId(null);
    };

    const resetSmartstoreForm = () => {
        setSmartstoreForm({
            name: "",
            client_id: "",
            client_secret: "",
            is_active: true
        });
        setSmartstoreEditId(null);
    };

    const handleUpsertCoupang = async () => {
        if (!coupangForm.name || !coupangForm.vendor_id || (!coupangForm.access_key && !coupangEditId) || (!coupangForm.secret_key && !coupangEditId)) {
            setNotification({ type: "error", message: "쿠팡 계정 정보가 부족합니다." });
            return;
        }
        try {
            const payload: any = {
                name: coupangForm.name,
                vendor_id: coupangForm.vendor_id,
                vendor_user_id: coupangForm.vendor_user_id,
                is_active: coupangForm.is_active
            };
            if (coupangForm.access_key) payload.access_key = coupangForm.access_key;
            if (coupangForm.secret_key) payload.secret_key = coupangForm.secret_key;

            const response = await fetch(
                coupangEditId ? `/api/settings/markets/coupang/accounts/${coupangEditId}` : "/api/settings/markets/coupang/accounts",
                {
                    method: coupangEditId ? "PATCH" : "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                }
            );
            if (!response.ok) {
                throw new Error("Failed to save coupang account");
            }
            setNotification({ type: "success", message: "쿠팡 계정이 저장되었습니다." });
            resetCoupangForm();
            loadMarketAccounts();
        } catch (error) {
            console.error("Failed to save coupang account", error);
            setNotification({ type: "error", message: "쿠팡 계정 저장에 실패했습니다." });
        }
    };

    const handleToggleCoupangActive = async (account: any) => {
        try {
            const response = await fetch(`/api/settings/markets/coupang/accounts/${account.id}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ is_active: !account.isActive })
            });
            if (!response.ok) {
                throw new Error("Failed to update coupang account");
            }
            loadMarketAccounts();
        } catch (error) {
            console.error("Failed to update coupang account", error);
            setNotification({ type: "error", message: "쿠팡 계정 상태 변경에 실패했습니다." });
        }
    };

    const handleDeleteCoupang = async (accountId: string) => {
        try {
            const response = await fetch(`/api/settings/markets/coupang/accounts/${accountId}`, {
                method: "DELETE"
            });
            if (!response.ok) {
                throw new Error("Failed to delete coupang account");
            }
            loadMarketAccounts();
        } catch (error) {
            console.error("Failed to delete coupang account", error);
            setNotification({ type: "error", message: "쿠팡 계정 삭제에 실패했습니다." });
        }
    };

    const handleUpsertSmartstore = async () => {
        if (!smartstoreForm.name || (!smartstoreForm.client_id && !smartstoreEditId) || (!smartstoreForm.client_secret && !smartstoreEditId)) {
            setNotification({ type: "error", message: "스마트스토어 계정 정보가 부족합니다." });
            return;
        }
        try {
            const payload: any = {
                name: smartstoreForm.name,
                is_active: smartstoreForm.is_active
            };
            if (smartstoreForm.client_id) payload.client_id = smartstoreForm.client_id;
            if (smartstoreForm.client_secret) payload.client_secret = smartstoreForm.client_secret;

            const response = await fetch(
                smartstoreEditId ? `/api/settings/markets/smartstore/accounts/${smartstoreEditId}` : "/api/settings/markets/smartstore/accounts",
                {
                    method: smartstoreEditId ? "PATCH" : "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                }
            );
            if (!response.ok) {
                throw new Error("Failed to save smartstore account");
            }
            setNotification({ type: "success", message: "스마트스토어 계정이 저장되었습니다." });
            resetSmartstoreForm();
            loadMarketAccounts();
        } catch (error) {
            console.error("Failed to save smartstore account", error);
            setNotification({ type: "error", message: "스마트스토어 계정 저장에 실패했습니다." });
        }
    };

    const handleToggleSmartstoreActive = async (account: any) => {
        try {
            const response = await fetch(`/api/settings/markets/smartstore/accounts/${account.id}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ is_active: !account.isActive })
            });
            if (!response.ok) {
                throw new Error("Failed to update smartstore account");
            }
            loadMarketAccounts();
        } catch (error) {
            console.error("Failed to update smartstore account", error);
            setNotification({ type: "error", message: "스마트스토어 계정 상태 변경에 실패했습니다." });
        }
    };

    const handleDeleteSmartstore = async (accountId: string) => {
        try {
            const response = await fetch(`/api/settings/markets/smartstore/accounts/${accountId}`, {
                method: "DELETE"
            });
            if (!response.ok) {
                throw new Error("Failed to delete smartstore account");
            }
            loadMarketAccounts();
        } catch (error) {
            console.error("Failed to delete smartstore account", error);
            setNotification({ type: "error", message: "스마트스토어 계정 삭제에 실패했습니다." });
        }
    };

    const handleUpsertOwnerclan = async () => {
        if (!ownerclanForm.username || !ownerclanForm.password) {
            setNotification({ type: "error", message: "오너클랜 계정 ID/PW가 필요합니다." });
            return;
        }
        setOwnerclanSubmitting(true);
        try {
            const response = await fetch("/api/settings/suppliers/ownerclan/accounts", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(ownerclanForm)
            });
            if (!response.ok) {
                throw new Error("Failed to save ownerclan account");
            }
            setNotification({ type: "success", message: "오너클랜 계정이 저장되었습니다." });
            setOwnerclanForm({
                user_type: "seller",
                username: "",
                password: "",
                set_primary: true,
                is_active: true
            });
            loadSupplierData();
        } catch (error) {
            console.error("Failed to save ownerclan account", error);
            setNotification({ type: "error", message: "오너클랜 계정 저장에 실패했습니다." });
        } finally {
            setOwnerclanSubmitting(false);
        }
    };

    const triggerOwnerclanSync = async (type: "items" | "orders" | "qna" | "categories") => {
        try {
            const response = await fetch(`/api/suppliers/ownerclan/sync/${type}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ params: {} })
            });
            if (!response.ok) {
                throw new Error("Failed to trigger ownerclan sync");
            }
            setNotification({ type: "success", message: "오너클랜 동기화 작업이 시작되었습니다." });
            loadSupplierData();
        } catch (error) {
            console.error("Failed to trigger ownerclan sync", error);
            setNotification({ type: "error", message: "오너클랜 동기화 시작에 실패했습니다." });
        }
    };

    const handleCreateAIKey = async () => {
        if (!aiForm.key) {
            setNotification({ type: "error", message: "API Key를 입력해주세요." });
            return;
        }
        try {
            const response = await fetch("/api/settings/ai/keys", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(aiForm)
            });
            if (!response.ok) {
                throw new Error("Failed to create AI key");
            }
            setNotification({ type: "success", message: "AI 키가 등록되었습니다." });
            setAiForm({ provider: "openai", key: "", is_active: true });
            loadAIKeys();
        } catch (error) {
            console.error("Failed to create AI key", error);
            setNotification({ type: "error", message: "AI 키 등록에 실패했습니다." });
        }
    };

    const handleToggleAIKey = async (keyId: string, currentActive: boolean) => {
        try {
            const response = await fetch(`/api/settings/ai/keys/${keyId}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ is_active: !currentActive })
            });
            if (!response.ok) {
                throw new Error("Failed to update AI key");
            }
            loadAIKeys();
        } catch (error) {
            console.error("Failed to update AI key", error);
            setNotification({ type: "error", message: "AI 키 상태 변경에 실패했습니다." });
        }
    };

    const handleDeleteAIKey = async (keyId: string) => {
        try {
            const response = await fetch(`/api/settings/ai/keys/${keyId}`, {
                method: "DELETE"
            });
            if (!response.ok) {
                throw new Error("Failed to delete AI key");
            }
            loadAIKeys();
        } catch (error) {
            console.error("Failed to delete AI key", error);
            setNotification({ type: "error", message: "AI 키 삭제에 실패했습니다." });
        }
    };

    const coupangColumns = ([
        { key: "name", title: "계정" },
        { key: "vendorId", title: "Vendor ID" },
        { key: "vendorUserId", title: "User ID" },
        {
            key: "isActive",
            title: "상태",
            render: (value: boolean) => (
                <Badge variant={value ? "success" : "secondary"}>{value ? "ACTIVE" : "OFF"}</Badge>
            )
        },
        { key: "accessKeyMasked", title: "Access Key" },
        { key: "secretKeyMasked", title: "Secret Key" },
        { key: "updatedAt", title: "업데이트" },
        {
            key: "actions",
            title: "작업",
            render: (_: any, row: any) => (
                <div className="flex items-center gap-1">
                    <Button
                        variant="outline"
                        size="xs"
                        onClick={(e) => {
                            e.stopPropagation();
                            setCoupangForm({
                                name: row.name || "",
                                vendor_id: row.vendorId || "",
                                vendor_user_id: row.vendorUserId || "",
                                access_key: "",
                                secret_key: "",
                                is_active: Boolean(row.isActive)
                            });
                            setCoupangEditId(row.id);
                        }}
                    >
                        편집
                    </Button>
                    <Button
                        variant="ghost"
                        size="xs"
                        onClick={(e) => {
                            e.stopPropagation();
                            handleToggleCoupangActive(row);
                        }}
                    >
                        {row.isActive ? "비활성" : "활성"}
                    </Button>
                    <Button
                        variant="danger"
                        size="xs"
                        onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteCoupang(row.id);
                        }}
                    >
                        삭제
                    </Button>
                </div>
            )
        }
    ]);

    const smartstoreColumns = ([
        { key: "name", title: "계정" },
        {
            key: "isActive",
            title: "상태",
            render: (value: boolean) => (
                <Badge variant={value ? "success" : "secondary"}>{value ? "ACTIVE" : "OFF"}</Badge>
            )
        },
        { key: "clientIdMasked", title: "Client ID" },
        { key: "clientSecretMasked", title: "Client Secret" },
        { key: "updatedAt", title: "업데이트" },
        {
            key: "actions",
            title: "작업",
            render: (_: any, row: any) => (
                <div className="flex items-center gap-1">
                    <Button
                        variant="outline"
                        size="xs"
                        onClick={(e) => {
                            e.stopPropagation();
                            setSmartstoreForm({
                                name: row.name || "",
                                client_id: "",
                                client_secret: "",
                                is_active: Boolean(row.isActive)
                            });
                            setSmartstoreEditId(row.id);
                        }}
                    >
                        편집
                    </Button>
                    <Button
                        variant="ghost"
                        size="xs"
                        onClick={(e) => {
                            e.stopPropagation();
                            handleToggleSmartstoreActive(row);
                        }}
                    >
                        {row.isActive ? "비활성" : "활성"}
                    </Button>
                    <Button
                        variant="danger"
                        size="xs"
                        onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteSmartstore(row.id);
                        }}
                    >
                        삭제
                    </Button>
                </div>
            )
        }
    ]);

    const ownerclanColumns = ([
        { key: "userType", title: "유형" },
        { key: "username", title: "계정" },
        {
            key: "isPrimary",
            title: "Primary",
            render: (value: boolean) => (
                <Badge variant={value ? "primary" : "secondary"}>{value ? "PRIMARY" : "—"}</Badge>
            )
        },
        {
            key: "isActive",
            title: "상태",
            render: (value: boolean) => (
                <Badge variant={value ? "success" : "secondary"}>{value ? "ACTIVE" : "OFF"}</Badge>
            )
        },
        { key: "tokenExpiresAt", title: "토큰 만료" },
        { key: "updatedAt", title: "업데이트" },
        {
            key: "actions",
            title: "작업",
            render: (_: any, row: any) => (
                <div className="flex items-center gap-1">
                    <Button
                        variant="outline"
                        size="xs"
                        onClick={(e) => {
                            e.stopPropagation();
                            setOwnerclanForm({
                                user_type: row.userType || "seller",
                                username: row.username || "",
                                password: "",
                                set_primary: Boolean(row.isPrimary),
                                is_active: Boolean(row.isActive)
                            });
                        }}
                    >
                        편집
                    </Button>
                </div>
            )
        }
    ]);

    const syncJobColumns = ([
        { key: "jobType", title: "작업" },
        {
            key: "status",
            title: "상태",
            render: (value: string) => (
                <Badge variant={value === "running" ? "warning" : value === "failed" ? "destructive" : "secondary"}>
                    {value?.toUpperCase?.() || value}
                </Badge>
            )
        },
        { key: "progress", title: "진행" },
        { key: "updatedAt", title: "업데이트" },
        { key: "lastError", title: "에러" },
    ]);

    const aiColumns = ([
        { key: "provider", title: "Provider" },
        { key: "keyMasked", title: "Key" },
        {
            key: "isActive",
            title: "상태",
            render: (value: boolean) => (
                <Badge variant={value ? "success" : "secondary"}>{value ? "ACTIVE" : "OFF"}</Badge>
            )
        },
        { key: "createdAt", title: "생성" },
        {
            key: "actions",
            title: "작업",
            render: (_: any, row: any) => (
                <div className="flex items-center gap-1">
                    <Button
                        variant="ghost"
                        size="xs"
                        onClick={(e) => {
                            e.stopPropagation();
                            handleToggleAIKey(row.id, row.isActive);
                        }}
                    >
                        {row.isActive ? "비활성" : "활성"}
                    </Button>
                    <Button
                        variant="danger"
                        size="xs"
                        onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteAIKey(row.id);
                        }}
                    >
                        삭제
                    </Button>
                </div>
            )
        }
    ]);

    return (
        <div className="space-y-3">
            <Breadcrumb
                items={[
                    { label: "설정" }
                ]}
            />

            <div className="flex items-center gap-1 px-3 py-2 border border-border bg-card rounded-sm">
                <button
                    className={`px-2 py-1 text-[10px] font-medium border-b-2 transition-colors ${activeTab === "orchestration" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                    onClick={() => setActiveTab("orchestration")}
                >
                    오케스트레이션
                </button>
                <button
                    className={`px-2 py-1 text-[10px] font-medium border-b-2 transition-colors ${activeTab === "lifecycle" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                    onClick={() => setActiveTab("lifecycle")}
                >
                    라이프사이클
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

            <div className="px-3 py-2 space-y-2">
                {activeTab === "orchestration" && (
                    <Card className="border border-border">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-xs flex items-center gap-1">
                                <Lock className="h-3 w-3 text-primary" />
                                오케스트레이션 설정
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            {isLoadingSettings && (
                                <div className="text-[10px] text-muted-foreground">설정을 불러오는 중...</div>
                            )}
                            <div className="grid gap-3 grid-cols-1 lg:grid-cols-2">
                                <div className="space-y-2 rounded-sm border border-border/70 bg-muted/10 p-3">
                                    <div className="text-[10px] font-semibold text-foreground">소싱 전략</div>
                                    <div className="grid gap-2 md:grid-cols-2">
                                        <div className="space-y-1">
                                            <label className="text-[10px] font-medium text-muted-foreground">소싱 키워드 제한</label>
                                            <Input
                                                type="number"
                                                value={orchestratorForm.sourcing_keyword_limit}
                                                onChange={(e) => setOrchestratorForm({
                                                    ...orchestratorForm,
                                                    sourcing_keyword_limit: toInt(e.target.value, 0)
                                                })}
                                                placeholder="30"
                                                size="sm"
                                            />
                                            <p className="text-[9px] text-muted-foreground">소싱에 사용할 키워드 수량입니다. (권장: 10 ~ 50)</p>
                                        </div>
                                        <div className="space-y-1">
                                            <label className="text-[10px] font-medium text-muted-foreground">Raw → 후보 전환 한도</label>
                                            <Input
                                                type="number"
                                                value={orchestratorForm.sourcing_import_limit}
                                                onChange={(e) => setOrchestratorForm({
                                                    ...orchestratorForm,
                                                    sourcing_import_limit: toInt(e.target.value, 0)
                                                })}
                                                placeholder="15000"
                                                size="sm"
                                            />
                                            <p className="text-[9px] text-muted-foreground">SupplierItemRaw에서 후보로 전환할 최대 수량입니다.</p>
                                        </div>
                                    </div>
                                    <div className="flex flex-col gap-1.5">
                                        <label className="flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground cursor-pointer">
                                            <input
                                                type="checkbox"
                                                className="w-3 h-3"
                                                checked={orchestratorForm.backfill_approve_enabled}
                                                onChange={(e) => setOrchestratorForm({
                                                    ...orchestratorForm,
                                                    backfill_approve_enabled: e.target.checked
                                                })}
                                            />
                                            소싱 후보 자동 승인 (목표 수량 부족 시)
                                        </label>
                                        <div className="grid gap-2 md:grid-cols-2">
                                            <div className="space-y-1">
                                                <label className="text-[10px] font-medium text-muted-foreground">자동 승인 상한</label>
                                            <Input
                                                type="number"
                                                value={orchestratorForm.backfill_approve_limit}
                                                onChange={(e) => setOrchestratorForm({
                                                    ...orchestratorForm,
                                                    backfill_approve_limit: toInt(e.target.value, 0)
                                                })}
                                                placeholder="2000"
                                                size="sm"
                                                disabled={!orchestratorForm.backfill_approve_enabled}
                                            />
                                                <p className="text-[9px] text-muted-foreground">하루 부족분 중 자동 승인할 최대 수량입니다.</p>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div className="space-y-2 rounded-sm border border-border/70 bg-muted/10 p-3">
                                    <div className="text-[10px] font-semibold text-foreground">가공 파이프라인</div>
                                    <div className="grid gap-2 md:grid-cols-2">
                                        <div className="space-y-1">
                                            <label className="text-[10px] font-medium text-muted-foreground">초기 가공 배치</label>
                                            <Input
                                                type="number"
                                                value={orchestratorForm.initial_processing_batch}
                                                onChange={(e) => setOrchestratorForm({
                                                    ...orchestratorForm,
                                                    initial_processing_batch: toInt(e.target.value, 0)
                                                })}
                                                placeholder="100"
                                                size="sm"
                                            />
                                            <p className="text-[9px] text-muted-foreground">사이클 시작 직후 동기 가공 처리량입니다.</p>
                                        </div>
                                        <div className="space-y-1">
                                            <label className="text-[10px] font-medium text-muted-foreground">지속 가공 배치</label>
                                            <Input
                                                type="number"
                                                value={orchestratorForm.processing_batch_size}
                                                onChange={(e) => setOrchestratorForm({
                                                    ...orchestratorForm,
                                                    processing_batch_size: toInt(e.target.value, 0)
                                                })}
                                                placeholder="50"
                                                size="sm"
                                            />
                                            <p className="text-[9px] text-muted-foreground">백그라운드 워커가 처리할 배치 크기입니다.</p>
                                        </div>
                                    </div>
                                </div>

                                <div className="space-y-2 rounded-sm border border-border/70 bg-muted/10 p-3 lg:col-span-2">
                                    <div className="text-[10px] font-semibold text-foreground">등록 파이프라인</div>
                                    <div className="grid gap-2 md:grid-cols-4">
                                        <div className="space-y-1 md:col-span-2">
                                            <label className="text-[10px] font-medium text-muted-foreground">일일 등록 한도</label>
                                            <Input
                                                type="number"
                                                value={orchestratorForm.listing_limit}
                                                onChange={(e) => setOrchestratorForm({
                                                    ...orchestratorForm,
                                                    listing_limit: toInt(e.target.value, 0)
                                                })}
                                                placeholder="15000"
                                                size="sm"
                                            />
                                            <p className="text-[9px] text-muted-foreground">가공 및 등록 대상 상품의 최대 수량입니다. (권장: 5,000 ~ 20,000)</p>
                                        </div>
                                        <div className="space-y-1">
                                            <label className="text-[10px] font-medium text-muted-foreground">동시 등록 수</label>
                                            <Input
                                                type="number"
                                                value={orchestratorForm.listing_concurrency}
                                                onChange={(e) => setOrchestratorForm({
                                                    ...orchestratorForm,
                                                    listing_concurrency: toInt(e.target.value, 1)
                                                })}
                                                placeholder="5"
                                                size="sm"
                                            />
                                            <p className="text-[9px] text-muted-foreground">마켓 등록 병렬도입니다.</p>
                                        </div>
                                        <div className="space-y-1">
                                            <label className="text-[10px] font-medium text-muted-foreground">지속 등록 배치</label>
                                            <Input
                                                type="number"
                                                value={orchestratorForm.listing_batch_limit}
                                                onChange={(e) => setOrchestratorForm({
                                                    ...orchestratorForm,
                                                    listing_batch_limit: toInt(e.target.value, 0)
                                                })}
                                                placeholder="100"
                                                size="sm"
                                            />
                                            <p className="text-[9px] text-muted-foreground">Continuous 모드에서 한 번에 등록할 수량입니다.</p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <label className="flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground cursor-pointer">
                                            <input
                                                type="checkbox"
                                                className="w-3 h-3"
                                                checked={orchestratorForm.continuous_mode}
                                                onChange={(e) => setOrchestratorForm({
                                                    ...orchestratorForm,
                                                    continuous_mode: e.target.checked
                                                })}
                                            />
                                            지속 등록 모드 (Continuous Listing)
                                        </label>
                                        <p className="text-[9px] text-muted-foreground">사이클 완료 후에도 백그라운드 등록을 유지합니다.</p>
                                    </div>
                                </div>
                            </div>

                            <div className="p-2 border border-warning/50 rounded-sm bg-warning/5">
                                <div className="flex items-start gap-1.5">
                                    <AlertTriangle className="h-3 w-3 text-warning flex-shrink-0" />
                                    <p className="text-[9px] text-warning-foreground">
                                        <span className="font-semibold">주의:</span> 등록 동시성/배치가 높으면 마켓 API 제한으로 계정이 일시 정지될 수 있습니다.
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
                                    sourcing_import_limit: 15000,
                                    initial_processing_batch: 100,
                                    processing_batch_size: 50,
                                    listing_concurrency: 5,
                                    listing_batch_limit: 100,
                                    backfill_approve_enabled: true,
                                    backfill_approve_limit: 2000,
                                    continuous_mode: false
                                })}
                            >
                                초기화
                            </Button>
                            <Button
                                onClick={saveOrchestratorSettings}
                                disabled={isLoading || isLoadingSettings}
                                size="sm"
                            >
                                {isLoading ? <span className="flex items-center gap-1">저장 중...</span> : <span className="flex items-center gap-1"><Save className="h-3 w-3" />저장</span>}
                            </Button>
                        </CardFooter>
                    </Card>
                )}

                {activeTab === "lifecycle" && (
                    <div className="space-y-3">
                        <Card className="border border-border">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-xs flex items-center gap-1">
                                    <Settings className="h-3 w-3 text-primary" />
                                    현재 적용 기준
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-2 text-[10px] text-muted-foreground">
                                <div className="grid gap-2 md:grid-cols-2">
                                    <div className="rounded-sm border border-border/70 bg-muted/10 p-3">
                                        <div className="text-[10px] font-semibold text-foreground">STEP 1 → 2</div>
                                        <div className="mt-1 flex flex-wrap gap-2">
                                            <Badge variant="secondary">판매 ≥ {lifecycleCriteriaForm.step1_to_step2.min_sales}</Badge>
                                            <Badge variant="secondary">CTR ≥ {lifecycleCriteriaForm.step1_to_step2.min_ctr}</Badge>
                                            <Badge variant="secondary">노출 ≥ {lifecycleCriteriaForm.step1_to_step2.min_views}</Badge>
                                            <Badge variant="secondary">등록일 ≥ {lifecycleCriteriaForm.step1_to_step2.min_days_listed}일</Badge>
                                        </div>
                                    </div>
                                    <div className="rounded-sm border border-border/70 bg-muted/10 p-3">
                                        <div className="text-[10px] font-semibold text-foreground">STEP 2 → 3</div>
                                        <div className="mt-1 flex flex-wrap gap-2">
                                            <Badge variant="secondary">판매 ≥ {lifecycleCriteriaForm.step2_to_step3.min_sales}</Badge>
                                            <Badge variant="secondary">재구매 ≥ {lifecycleCriteriaForm.step2_to_step3.min_repeat_purchase}</Badge>
                                            <Badge variant="secondary">유지율 ≥ {lifecycleCriteriaForm.step2_to_step3.min_customer_retention}</Badge>
                                            <Badge variant="secondary">매출 ≥ {lifecycleCriteriaForm.step2_to_step3.min_revenue}</Badge>
                                            <Badge variant="secondary">체류 ≥ {lifecycleCriteriaForm.step2_to_step3.min_days_in_step2}일</Badge>
                                        </div>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="border border-border">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-xs flex items-center gap-1">
                                    <Settings className="h-3 w-3 text-primary" />
                                    라이프사이클 전환 기준
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                {categoryRowValidation.errors.length > 0 && (
                                    <div className="text-[10px] text-destructive">
                                        카테고리 보정 오류 {categoryRowValidation.errors.length}건이 있습니다. 저장 전에 수정해 주세요.
                                    </div>
                                )}
                                <div className="grid gap-3 grid-cols-1 lg:grid-cols-2">
                                    <div className="space-y-2 rounded-sm border border-border/70 bg-muted/10 p-3">
                                        <div className="text-[10px] font-semibold text-foreground">STEP 1 → 2</div>
                                        <div className="grid gap-2 md:grid-cols-2">
                                            <div className="space-y-1">
                                                <label className="text-[10px] font-medium text-muted-foreground">최소 판매</label>
                                                <Input
                                                    type="number"
                                                    value={lifecycleCriteriaForm.step1_to_step2.min_sales}
                                                    onChange={(e) => setLifecycleCriteriaForm((prev) => ({
                                                        ...prev,
                                                        step1_to_step2: {
                                                            ...prev.step1_to_step2,
                                                            min_sales: toInt(e.target.value, 0)
                                                        }
                                                    }))}
                                                    size="sm"
                                                />
                                            </div>
                                            <div className="space-y-1">
                                                <label className="text-[10px] font-medium text-muted-foreground">최소 CTR</label>
                                                <Input
                                                    type="number"
                                                    step="0.01"
                                                    value={lifecycleCriteriaForm.step1_to_step2.min_ctr}
                                                    onChange={(e) => setLifecycleCriteriaForm((prev) => ({
                                                        ...prev,
                                                        step1_to_step2: {
                                                            ...prev.step1_to_step2,
                                                            min_ctr: toFloat(e.target.value, 0)
                                                        }
                                                    }))}
                                                    size="sm"
                                                />
                                            </div>
                                            <div className="space-y-1">
                                                <label className="text-[10px] font-medium text-muted-foreground">최소 노출</label>
                                                <Input
                                                    type="number"
                                                    value={lifecycleCriteriaForm.step1_to_step2.min_views}
                                                    onChange={(e) => setLifecycleCriteriaForm((prev) => ({
                                                        ...prev,
                                                        step1_to_step2: {
                                                            ...prev.step1_to_step2,
                                                            min_views: toInt(e.target.value, 0)
                                                        }
                                                    }))}
                                                    size="sm"
                                                />
                                            </div>
                                            <div className="space-y-1">
                                                <label className="text-[10px] font-medium text-muted-foreground">최소 등록일</label>
                                                <Input
                                                    type="number"
                                                    value={lifecycleCriteriaForm.step1_to_step2.min_days_listed}
                                                    onChange={(e) => setLifecycleCriteriaForm((prev) => ({
                                                        ...prev,
                                                        step1_to_step2: {
                                                            ...prev.step1_to_step2,
                                                            min_days_listed: toInt(e.target.value, 0)
                                                        }
                                                    }))}
                                                    size="sm"
                                                />
                                            </div>
                                        </div>
                                        <p className="text-[9px] text-muted-foreground">CTR은 0.02 = 2% 기준입니다.</p>
                                    </div>

                                    <div className="space-y-2 rounded-sm border border-border/70 bg-muted/10 p-3">
                                        <div className="text-[10px] font-semibold text-foreground">STEP 2 → 3</div>
                                        <div className="grid gap-2 md:grid-cols-2">
                                            <div className="space-y-1">
                                                <label className="text-[10px] font-medium text-muted-foreground">최소 판매</label>
                                                <Input
                                                    type="number"
                                                    value={lifecycleCriteriaForm.step2_to_step3.min_sales}
                                                    onChange={(e) => setLifecycleCriteriaForm((prev) => ({
                                                        ...prev,
                                                        step2_to_step3: {
                                                            ...prev.step2_to_step3,
                                                            min_sales: toInt(e.target.value, 0)
                                                        }
                                                    }))}
                                                    size="sm"
                                                />
                                            </div>
                                            <div className="space-y-1">
                                                <label className="text-[10px] font-medium text-muted-foreground">재구매 기준</label>
                                                <Input
                                                    type="number"
                                                    value={lifecycleCriteriaForm.step2_to_step3.min_repeat_purchase}
                                                    onChange={(e) => setLifecycleCriteriaForm((prev) => ({
                                                        ...prev,
                                                        step2_to_step3: {
                                                            ...prev.step2_to_step3,
                                                            min_repeat_purchase: toInt(e.target.value, 0)
                                                        }
                                                    }))}
                                                    size="sm"
                                                />
                                            </div>
                                            <div className="space-y-1">
                                                <label className="text-[10px] font-medium text-muted-foreground">고객 유지율</label>
                                                <Input
                                                    type="number"
                                                    step="0.01"
                                                    value={lifecycleCriteriaForm.step2_to_step3.min_customer_retention}
                                                    onChange={(e) => setLifecycleCriteriaForm((prev) => ({
                                                        ...prev,
                                                        step2_to_step3: {
                                                            ...prev.step2_to_step3,
                                                            min_customer_retention: toFloat(e.target.value, 0)
                                                        }
                                                    }))}
                                                    size="sm"
                                                />
                                            </div>
                                            <div className="space-y-1">
                                                <label className="text-[10px] font-medium text-muted-foreground">최소 매출</label>
                                                <Input
                                                    type="number"
                                                    value={lifecycleCriteriaForm.step2_to_step3.min_revenue}
                                                    onChange={(e) => setLifecycleCriteriaForm((prev) => ({
                                                        ...prev,
                                                        step2_to_step3: {
                                                            ...prev.step2_to_step3,
                                                            min_revenue: toInt(e.target.value, 0)
                                                        }
                                                    }))}
                                                    size="sm"
                                                />
                                            </div>
                                            <div className="space-y-1">
                                                <label className="text-[10px] font-medium text-muted-foreground">STEP 2 체류</label>
                                                <Input
                                                    type="number"
                                                    value={lifecycleCriteriaForm.step2_to_step3.min_days_in_step2}
                                                    onChange={(e) => setLifecycleCriteriaForm((prev) => ({
                                                        ...prev,
                                                        step2_to_step3: {
                                                            ...prev.step2_to_step3,
                                                            min_days_in_step2: toInt(e.target.value, 0)
                                                        }
                                                    }))}
                                                    size="sm"
                                                />
                                            </div>
                                        </div>
                                        <p className="text-[9px] text-muted-foreground">고객 유지율은 0.1 = 10% 기준입니다.</p>
                                    </div>
                                </div>

                                <div className="space-y-2 rounded-sm border border-border/70 bg-muted/10 p-3">
                                    <div className="text-[10px] font-semibold text-foreground">카테고리별 보정</div>
                                    {(() => {
                                        const diff = computeCategoryDiff(categoryRows, lastSavedCategoryRows);
                                        const total = diff.added.length + diff.removed.length + diff.changed.length;
                                        if (total === 0) {
                                            return (
                                                <div className="text-[9px] text-muted-foreground">마지막 저장 이후 변경 사항이 없습니다.</div>
                                            );
                                        }
                                                return (
                                                    <div className="space-y-0.5">
                                                        <div className="text-[9px] text-muted-foreground">
                                                            변경 사항: 추가 {diff.added.length} / 삭제 {diff.removed.length} / 수정 {diff.changed.length}
                                                        </div>
                                                {renderDiffLine("추가", diff.added, handleDiffClick)}
                                                {renderDiffLine("삭제", diff.removed)}
                                                {renderDiffLine("수정", diff.changed, handleDiffClick)}
                                                    </div>
                                                );
                                            })()}
                                    <div className="grid gap-2 md:grid-cols-3">
                                        <div className="space-y-1 md:col-span-2">
                                            <label className="text-[10px] font-medium text-muted-foreground">카테고리명</label>
                                        <Input
                                            value={categoryOverrideDraft.name}
                                            onChange={(e) => setCategoryOverrideDraft((prev) => ({ ...prev, name: e.target.value }))}
                                            size="sm"
                                            placeholder="예: 패션의류"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">min_sales</label>
                                        <Input
                                            type="number"
                                            value={categoryOverrideDraft.min_sales}
                                            onChange={(e) => setCategoryOverrideDraft((prev) => ({
                                                ...prev,
                                                min_sales: e.target.value
                                            }))}
                                            size="sm"
                                        />
                                    </div>
                                </div>
                                <div className="grid gap-2 md:grid-cols-4">
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">min_ctr</label>
                                        <Input
                                            type="number"
                                            step="0.01"
                                            value={categoryOverrideDraft.min_ctr}
                                            onChange={(e) => setCategoryOverrideDraft((prev) => ({
                                                ...prev,
                                                min_ctr: e.target.value
                                            }))}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">min_views</label>
                                        <Input
                                            type="number"
                                            value={categoryOverrideDraft.min_views}
                                            onChange={(e) => setCategoryOverrideDraft((prev) => ({
                                                ...prev,
                                                min_views: e.target.value
                                            }))}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">min_days_listed</label>
                                        <Input
                                            type="number"
                                            value={categoryOverrideDraft.min_days_listed}
                                            onChange={(e) => setCategoryOverrideDraft((prev) => ({
                                                ...prev,
                                                min_days_listed: e.target.value
                                            }))}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">min_repeat_purchase</label>
                                        <Input
                                            type="number"
                                            value={categoryOverrideDraft.min_repeat_purchase}
                                            onChange={(e) => setCategoryOverrideDraft((prev) => ({
                                                ...prev,
                                                min_repeat_purchase: e.target.value
                                            }))}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">min_customer_retention</label>
                                        <Input
                                            type="number"
                                            step="0.01"
                                            value={categoryOverrideDraft.min_customer_retention}
                                            onChange={(e) => setCategoryOverrideDraft((prev) => ({
                                                ...prev,
                                                min_customer_retention: e.target.value
                                            }))}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">min_revenue</label>
                                        <Input
                                            type="number"
                                            value={categoryOverrideDraft.min_revenue}
                                            onChange={(e) => setCategoryOverrideDraft((prev) => ({
                                                ...prev,
                                                min_revenue: e.target.value
                                            }))}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">min_days_in_step2</label>
                                        <Input
                                            type="number"
                                            value={categoryOverrideDraft.min_days_in_step2}
                                            onChange={(e) => setCategoryOverrideDraft((prev) => ({
                                                ...prev,
                                                min_days_in_step2: e.target.value
                                            }))}
                                            size="sm"
                                        />
                                    </div>
                                </div>
                                <div className="flex justify-end">
                                    <Button size="xs" variant="outline" onClick={applyCategoryOverride}>
                                        추가/업데이트
                                    </Button>
                                    <Button
                                        size="xs"
                                        variant="ghost"
                                        onClick={() => {
                                            setCategoryRows((prev) => {
                                                const next = [
                                                    ...prev,
                                                    {
                                                        name: "",
                                                        min_sales: "",
                                                        min_ctr: "",
                                                        min_views: "",
                                                        min_days_listed: "",
                                                        min_repeat_purchase: "",
                                                        min_customer_retention: "",
                                                        min_revenue: "",
                                                        min_days_in_step2: ""
                                                    }
                                                ];
                                                return autoSortEnabled ? getSortedRows(next, categorySort.key, categorySort.direction) : next;
                                            });
                                        }}
                                    >
                                        행 추가
                                    </Button>
                                </div>
                                <div className="flex flex-wrap items-center gap-2 text-[9px] text-muted-foreground">
                                    <label className="flex items-center gap-1">
                                        정렬 기준
                                        <Select
                                            value={categorySort.key}
                                            onValueChange={(value) => setCategorySort((prev) => ({ ...prev, key: value }))}
                                            options={[
                                                { value: "name", label: "카테고리" },
                                                { value: "min_sales", label: "min_sales" },
                                                { value: "min_ctr", label: "min_ctr" },
                                                { value: "min_views", label: "min_views" },
                                                { value: "min_days_listed", label: "min_days_listed" },
                                                { value: "min_repeat_purchase", label: "min_repeat_purchase" },
                                                { value: "min_customer_retention", label: "min_customer_retention" },
                                                { value: "min_revenue", label: "min_revenue" },
                                                { value: "min_days_in_step2", label: "min_days_in_step2" }
                                            ]}
                                            size="xs"
                                        />
                                    </label>
                                    <label className="flex items-center gap-1">
                                        방향
                                        <Select
                                            value={categorySort.direction}
                                            onValueChange={(value) => setCategorySort((prev) => ({ ...prev, direction: value as "asc" | "desc" }))}
                                            options={[
                                                { value: "asc", label: "오름차순" },
                                                { value: "desc", label: "내림차순" }
                                            ]}
                                            size="xs"
                                        />
                                    </label>
                                    <Button
                                        size="xs"
                                        variant="outline"
                                        onClick={() => {
                                            setAutoSortEnabled(true);
                                            sortCategoryRows(categorySort.key, categorySort.direction);
                                        }}
                                    >
                                        정렬 적용
                                    </Button>
                                    <label className="flex items-center gap-1">
                                        <input
                                            type="checkbox"
                                            className="w-3 h-3"
                                            checked={autoSortEnabled}
                                            onChange={(e) => setAutoSortEnabled(e.target.checked)}
                                        />
                                        자동 정렬
                                    </label>
                                    <Button
                                        size="xs"
                                        variant="ghost"
                                        onClick={() => {
                                            if (lastSavedCategoryRows.length === 0) {
                                                return;
                                            }
                                            setAutoSortEnabled(false);
                                            setCategoryRows([...lastSavedCategoryRows]);
                                        }}
                                        disabled={lastSavedCategoryRows.length === 0}
                                    >
                                        원래 순서
                                    </Button>
                                    <Button size="xs" variant="outline" onClick={exportCategoryCsv}>
                                        CSV 내보내기
                                    </Button>
                                    <Button size="xs" variant="ghost" onClick={exportCategoryCsvTemplate}>
                                        템플릿
                                    </Button>
                                    <Button size="xs" variant="ghost" onClick={exportCategoryCsvSample}>
                                        샘플
                                    </Button>
                                    <Button
                                        size="xs"
                                        variant="outline"
                                        onClick={() => {
                                            setCsvImportMode("merge");
                                            csvInputRef.current?.click();
                                        }}
                                    >
                                        CSV 병합
                                    </Button>
                                    <Button
                                        size="xs"
                                        variant="outline"
                                        onClick={() => {
                                            setCsvImportMode("replace");
                                            csvInputRef.current?.click();
                                        }}
                                    >
                                        CSV 덮어쓰기
                                    </Button>
                                    <input
                                        ref={csvInputRef}
                                        type="file"
                                        accept=".csv,text/csv"
                                        className="hidden"
                                        onChange={(e) => importCategoryCsv(e.target.files?.[0] || null, csvImportMode)}
                                    />
                                    <Input
                                        value={categoryFilter}
                                        onChange={(e) => setCategoryFilter(e.target.value)}
                                        placeholder="검색"
                                        size="xs"
                                        className="max-w-[160px]"
                                    />
                                    <span>
                                        결과 {filteredCategoryRows.length} / {categoryRows.length}
                                    </span>
                                    {categoryFilter && (
                                        <Button size="xs" variant="ghost" onClick={() => setCategoryFilter("")}>
                                            검색 해제
                                        </Button>
                                    )}
                                </div>
                                {pendingCsvRows && (
                                    <div className="rounded-sm border border-border/60 bg-muted/10 p-2 text-[9px] text-muted-foreground">
                                        {(() => {
                                            const previewValidation = collectCategoryRowErrors(pendingCsvRows);
                                            return (
                                                <>
                                        <div className="flex flex-wrap items-center gap-2">
                                            <span>CSV 미리보기: {pendingCsvRows.length}건</span>
                                            <Select
                                                value={pendingCsvMode}
                                                onValueChange={(value) => setPendingCsvMode(value as "merge" | "replace")}
                                                options={[
                                                    { value: "merge", label: "병합" },
                                                    { value: "replace", label: "덮어쓰기" }
                                                ]}
                                                size="xs"
                                            />
                                        </div>
                                        {previewValidation.errors.length > 0 ? (
                                            <div className="mt-1 text-[9px] text-destructive">
                                                CSV 오류 {previewValidation.errors.length}건이 있습니다. 수정 후 적용하세요.
                                            </div>
                                        ) : null}
                                        <div className="mt-2 overflow-x-auto">
                                            <table className="min-w-[720px] text-[9px] border border-border/60 bg-background">
                                                <thead className="bg-muted/40">
                                                    <tr>
                                                        <th className="px-2 py-1 text-left font-semibold">카테고리</th>
                                                        <th className="px-2 py-1 text-left font-semibold">min_sales</th>
                                                        <th className="px-2 py-1 text-left font-semibold">min_ctr</th>
                                                        <th className="px-2 py-1 text-left font-semibold">min_views</th>
                                                        <th className="px-2 py-1 text-left font-semibold">min_days_listed</th>
                                                        <th className="px-2 py-1 text-left font-semibold">min_repeat_purchase</th>
                                                        <th className="px-2 py-1 text-left font-semibold">min_customer_retention</th>
                                                        <th className="px-2 py-1 text-left font-semibold">min_revenue</th>
                                                        <th className="px-2 py-1 text-left font-semibold">min_days_in_step2</th>
                                                        <th className="px-2 py-1 text-left font-semibold">관리</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {pendingCsvRows.slice(0, 5).map((row, index) => {
                                                        const hasError = Boolean(previewValidation.rowErrors[index]?.length);
                                                        return (
                                                        <tr key={`${row.name}-${index}`} className={`border-t border-border/50 ${hasError ? "bg-destructive/5" : ""}`}>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    value={row.name || ""}
                                                                    onChange={(e) => updatePendingCsvRowField(index, "name", e.target.value)}
                                                                    size="xs"
                                                                    error={Boolean(previewValidation.fieldErrors[index]?.name)}
                                                                    title={previewValidation.fieldErrors[index]?.name}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    value={row.min_sales || ""}
                                                                    onChange={(e) => updatePendingCsvRowField(index, "min_sales", e.target.value)}
                                                                    size="xs"
                                                                    error={Boolean(previewValidation.fieldErrors[index]?.min_sales)}
                                                                    title={previewValidation.fieldErrors[index]?.min_sales}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    step="0.01"
                                                                    value={row.min_ctr || ""}
                                                                    onChange={(e) => updatePendingCsvRowField(index, "min_ctr", e.target.value)}
                                                                    size="xs"
                                                                    error={Boolean(previewValidation.fieldErrors[index]?.min_ctr)}
                                                                    title={previewValidation.fieldErrors[index]?.min_ctr}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    value={row.min_views || ""}
                                                                    onChange={(e) => updatePendingCsvRowField(index, "min_views", e.target.value)}
                                                                    size="xs"
                                                                    error={Boolean(previewValidation.fieldErrors[index]?.min_views)}
                                                                    title={previewValidation.fieldErrors[index]?.min_views}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    value={row.min_days_listed || ""}
                                                                    onChange={(e) => updatePendingCsvRowField(index, "min_days_listed", e.target.value)}
                                                                    size="xs"
                                                                    error={Boolean(previewValidation.fieldErrors[index]?.min_days_listed)}
                                                                    title={previewValidation.fieldErrors[index]?.min_days_listed}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    value={row.min_repeat_purchase || ""}
                                                                    onChange={(e) => updatePendingCsvRowField(index, "min_repeat_purchase", e.target.value)}
                                                                    size="xs"
                                                                    error={Boolean(previewValidation.fieldErrors[index]?.min_repeat_purchase)}
                                                                    title={previewValidation.fieldErrors[index]?.min_repeat_purchase}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    step="0.01"
                                                                    value={row.min_customer_retention || ""}
                                                                    onChange={(e) => updatePendingCsvRowField(index, "min_customer_retention", e.target.value)}
                                                                    size="xs"
                                                                    error={Boolean(previewValidation.fieldErrors[index]?.min_customer_retention)}
                                                                    title={previewValidation.fieldErrors[index]?.min_customer_retention}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    value={row.min_revenue || ""}
                                                                    onChange={(e) => updatePendingCsvRowField(index, "min_revenue", e.target.value)}
                                                                    size="xs"
                                                                    error={Boolean(previewValidation.fieldErrors[index]?.min_revenue)}
                                                                    title={previewValidation.fieldErrors[index]?.min_revenue}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    value={row.min_days_in_step2 || ""}
                                                                    onChange={(e) => updatePendingCsvRowField(index, "min_days_in_step2", e.target.value)}
                                                                    size="xs"
                                                                    error={Boolean(previewValidation.fieldErrors[index]?.min_days_in_step2)}
                                                                    title={previewValidation.fieldErrors[index]?.min_days_in_step2}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Button size="xs" variant="ghost" onClick={() => removePendingCsvRow(index)}>
                                                                    삭제
                                                                </Button>
                                                            </td>
                                                        </tr>
                                                    );
                                                    })}
                                                </tbody>
                                            </table>
                                            {pendingCsvRows.length > 5 ? (
                                                <div className="mt-1 text-[9px] text-muted-foreground">
                                                    외 {pendingCsvRows.length - 5}건
                                                </div>
                                            ) : null}
                                        </div>
                                        <div className="mt-1 flex flex-wrap gap-2">
                                            <Button size="xs" variant="outline" onClick={applyCsvImport} disabled={previewValidation.errors.length > 0}>
                                                적용
                                            </Button>
                                            <Button size="xs" variant="outline" onClick={addPendingCsvRow}>
                                                행 추가
                                            </Button>
                                            <Button size="xs" variant="ghost" onClick={cancelCsvImport}>
                                                취소
                                            </Button>
                                        </div>
                                                </>
                                            );
                                        })()}
                                    </div>
                                )}
                                <div className="space-y-1">
                                    {filteredCategoryRows.length === 0 ? (
                                        <div className="text-[9px] text-muted-foreground">등록된 카테고리 보정이 없습니다.</div>
                                    ) : (
                                        <div className="overflow-x-auto">
                                            <table className="w-full text-[10px] border border-border/60">
                                                <thead className="bg-muted/30">
                                                    <tr className="text-left">
                                                        <th className="px-2 py-1 font-semibold">카테고리</th>
                                                        <th className="px-2 py-1 font-semibold">min_sales</th>
                                                        <th className="px-2 py-1 font-semibold">min_ctr</th>
                                                        <th className="px-2 py-1 font-semibold">min_views</th>
                                                        <th className="px-2 py-1 font-semibold">min_days_listed</th>
                                                        <th className="px-2 py-1 font-semibold">min_repeat_purchase</th>
                                                        <th className="px-2 py-1 font-semibold">min_customer_retention</th>
                                                        <th className="px-2 py-1 font-semibold">min_revenue</th>
                                                        <th className="px-2 py-1 font-semibold">min_days_in_step2</th>
                                                        <th className="px-2 py-1 font-semibold">관리</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {filteredCategoryRows.map(({ row, index: rowIndex }) => (
                                                        <tr
                                                            key={`${row.name}-${rowIndex}`}
                                                            id={`category-row-${rowIndex}`}
                                                            className={`border-t border-border/60 ${categoryRowValidation.rowErrors[rowIndex]?.length ? "bg-destructive/5" : ""} ${highlightRowIndex === rowIndex ? "ring-1 ring-primary/40" : ""}`}
                                                        >
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    value={row.name}
                                                                    onChange={(e) => {
                                                                        const value = e.target.value;
                                                                        setCategoryRows((prev) => prev.map((item, idx) => (
                                                                            idx === rowIndex ? { ...item, name: value } : item
                                                                        )));
                                                                    }}
                                                                    size="xs"
                                                                    error={Boolean(getFieldError(rowIndex, "name"))}
                                                                    title={getFieldError(rowIndex, "name")}
                                                                    aria-invalid={Boolean(getFieldError(rowIndex, "name"))}
                                                                    className={getMatchClass(row.name)}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    value={row.min_sales}
                                                                    onChange={(e) => {
                                                                        const value = e.target.value;
                                                                        setCategoryRows((prev) => prev.map((item, idx) => (
                                                                            idx === rowIndex ? { ...item, min_sales: value } : item
                                                                        )));
                                                                    }}
                                                                    size="xs"
                                                                    error={Boolean(getFieldError(rowIndex, "min_sales"))}
                                                                    title={getFieldError(rowIndex, "min_sales")}
                                                                    aria-invalid={Boolean(getFieldError(rowIndex, "min_sales"))}
                                                                    className={getMatchClass(row.min_sales)}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    step="0.01"
                                                                    value={row.min_ctr}
                                                                    onChange={(e) => {
                                                                        const value = e.target.value;
                                                                        setCategoryRows((prev) => prev.map((item, idx) => (
                                                                            idx === rowIndex ? { ...item, min_ctr: value } : item
                                                                        )));
                                                                    }}
                                                                    size="xs"
                                                                    error={Boolean(getFieldError(rowIndex, "min_ctr"))}
                                                                    title={getFieldError(rowIndex, "min_ctr")}
                                                                    aria-invalid={Boolean(getFieldError(rowIndex, "min_ctr"))}
                                                                    className={getMatchClass(row.min_ctr)}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    value={row.min_views}
                                                                    onChange={(e) => {
                                                                        const value = e.target.value;
                                                                        setCategoryRows((prev) => prev.map((item, idx) => (
                                                                            idx === rowIndex ? { ...item, min_views: value } : item
                                                                        )));
                                                                    }}
                                                                    size="xs"
                                                                    error={Boolean(getFieldError(rowIndex, "min_views"))}
                                                                    title={getFieldError(rowIndex, "min_views")}
                                                                    aria-invalid={Boolean(getFieldError(rowIndex, "min_views"))}
                                                                    className={getMatchClass(row.min_views)}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    value={row.min_days_listed}
                                                                    onChange={(e) => {
                                                                        const value = e.target.value;
                                                                        setCategoryRows((prev) => prev.map((item, idx) => (
                                                                            idx === rowIndex ? { ...item, min_days_listed: value } : item
                                                                        )));
                                                                    }}
                                                                    size="xs"
                                                                    error={Boolean(getFieldError(rowIndex, "min_days_listed"))}
                                                                    title={getFieldError(rowIndex, "min_days_listed")}
                                                                    aria-invalid={Boolean(getFieldError(rowIndex, "min_days_listed"))}
                                                                    className={getMatchClass(row.min_days_listed)}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    value={row.min_repeat_purchase}
                                                                    onChange={(e) => {
                                                                        const value = e.target.value;
                                                                        setCategoryRows((prev) => prev.map((item, idx) => (
                                                                            idx === rowIndex ? { ...item, min_repeat_purchase: value } : item
                                                                        )));
                                                                    }}
                                                                    size="xs"
                                                                    error={Boolean(getFieldError(rowIndex, "min_repeat_purchase"))}
                                                                    title={getFieldError(rowIndex, "min_repeat_purchase")}
                                                                    aria-invalid={Boolean(getFieldError(rowIndex, "min_repeat_purchase"))}
                                                                    className={getMatchClass(row.min_repeat_purchase)}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    step="0.01"
                                                                    value={row.min_customer_retention}
                                                                    onChange={(e) => {
                                                                        const value = e.target.value;
                                                                        setCategoryRows((prev) => prev.map((item, idx) => (
                                                                            idx === rowIndex ? { ...item, min_customer_retention: value } : item
                                                                        )));
                                                                    }}
                                                                    size="xs"
                                                                    error={Boolean(getFieldError(rowIndex, "min_customer_retention"))}
                                                                    title={getFieldError(rowIndex, "min_customer_retention")}
                                                                    aria-invalid={Boolean(getFieldError(rowIndex, "min_customer_retention"))}
                                                                    className={getMatchClass(row.min_customer_retention)}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    value={row.min_revenue}
                                                                    onChange={(e) => {
                                                                        const value = e.target.value;
                                                                        setCategoryRows((prev) => prev.map((item, idx) => (
                                                                            idx === rowIndex ? { ...item, min_revenue: value } : item
                                                                        )));
                                                                    }}
                                                                    size="xs"
                                                                    error={Boolean(getFieldError(rowIndex, "min_revenue"))}
                                                                    title={getFieldError(rowIndex, "min_revenue")}
                                                                    aria-invalid={Boolean(getFieldError(rowIndex, "min_revenue"))}
                                                                    className={getMatchClass(row.min_revenue)}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <Input
                                                                    type="number"
                                                                    value={row.min_days_in_step2}
                                                                    onChange={(e) => {
                                                                        const value = e.target.value;
                                                                        setCategoryRows((prev) => prev.map((item, idx) => (
                                                                            idx === rowIndex ? { ...item, min_days_in_step2: value } : item
                                                                        )));
                                                                    }}
                                                                    size="xs"
                                                                    error={Boolean(getFieldError(rowIndex, "min_days_in_step2"))}
                                                                    title={getFieldError(rowIndex, "min_days_in_step2")}
                                                                    aria-invalid={Boolean(getFieldError(rowIndex, "min_days_in_step2"))}
                                                                    className={getMatchClass(row.min_days_in_step2)}
                                                                />
                                                            </td>
                                                            <td className="px-2 py-1">
                                                                <div className="flex items-center gap-1">
                                                                    <Button size="xs" variant="ghost" onClick={() => removeCategoryOverride(rowIndex)}>
                                                                        삭제
                                                                    </Button>
                                                                    <Button size="xs" variant="ghost" onClick={() => duplicateCategoryRow(rowIndex)}>
                                                                        복제
                                                                    </Button>
                                                                    <Button
                                                                        size="xs"
                                                                        variant="ghost"
                                                                        onClick={() => moveCategoryRow(rowIndex, "up")}
                                                                        disabled={rowIndex === 0}
                                                                    >
                                                                        위
                                                                    </Button>
                                                                    <Button
                                                                        size="xs"
                                                                        variant="ghost"
                                                                        onClick={() => moveCategoryRow(rowIndex, "down")}
                                                                        disabled={rowIndex === categoryRows.length - 1}
                                                                    >
                                                                        아래
                                                                    </Button>
                                                                </div>
                                                                {categoryRowValidation.rowErrors[rowIndex]?.length ? (
                                                                    <div className="mt-1 text-[9px] text-destructive">
                                                                        {categoryRowValidation.rowErrors[rowIndex][0]}
                                                                    </div>
                                                                ) : null}
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    )}
                                </div>
                            </div>
                            </CardContent>
                            <CardFooter className="flex justify-end pt-2 border-t border-border/50">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setLifecycleCriteriaForm({
                                        step1_to_step2: { ...defaultLifecycleCriteria.step1_to_step2 },
                                        step2_to_step3: { ...defaultLifecycleCriteria.step2_to_step3 },
                                        category_adjusted_raw: JSON.stringify(defaultLifecycleCriteria.category_adjusted, null, 2)
                                    })}
                                >
                                    초기화
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => {
                                        const parsed = parseCategoryAdjusted(lifecycleCriteriaForm.category_adjusted_raw);
                                        if (!parsed) {
                                            setNotification({ type: "error", message: "카테고리 보정 JSON 형식이 올바르지 않습니다." });
                                            return;
                                        }
                                        const rows = Object.entries(parsed).map(([name, rules]) => ({
                                            name,
                                            min_sales: rules?.min_sales?.toString?.() || "",
                                            min_ctr: rules?.min_ctr?.toString?.() || "",
                                            min_views: rules?.min_views?.toString?.() || "",
                                            min_days_listed: rules?.min_days_listed?.toString?.() || "",
                                            min_repeat_purchase: rules?.min_repeat_purchase?.toString?.() || "",
                                            min_customer_retention: rules?.min_customer_retention?.toString?.() || "",
                                            min_revenue: rules?.min_revenue?.toString?.() || "",
                                            min_days_in_step2: rules?.min_days_in_step2?.toString?.() || ""
                                        }));
                                        setCategoryRows(rows);
                                    }}
                                >
                                    JSON 반영
                                </Button>
                                <Button
                                    onClick={saveLifecycleCriteria}
                                    disabled={isSavingLifecycle || isLoadingSettings || categoryRowValidation.errors.length > 0}
                                    size="sm"
                                >
                                    {isSavingLifecycle ? <span className="flex items-center gap-1">저장 중...</span> : <span className="flex items-center gap-1"><Save className="h-3 w-3" />저장</span>}
                                </Button>
                            </CardFooter>
                        </Card>
                    </div>
                )}

                {activeTab === "market" && (
                    <div className="space-y-3">
                        <Card className="border border-border">
                            <CardHeader className="pb-2 flex flex-row items-center justify-between">
                                <CardTitle className="text-xs flex items-center gap-1">
                                    <Settings className="h-3 w-3 text-primary" />
                                    쿠팡 계정
                                </CardTitle>
                                <Button variant="outline" size="xs" onClick={loadMarketAccounts}>
                                    <RefreshCw className="h-3 w-3 mr-1" />
                                    새로고침
                                </Button>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                <div className="grid gap-2 md:grid-cols-3">
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">계정 이름</label>
                                        <Input
                                            value={coupangForm.name}
                                            onChange={(e) => setCoupangForm({ ...coupangForm, name: e.target.value })}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">Vendor ID</label>
                                        <Input
                                            value={coupangForm.vendor_id}
                                            onChange={(e) => setCoupangForm({ ...coupangForm, vendor_id: e.target.value })}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">Vendor User ID</label>
                                        <Input
                                            value={coupangForm.vendor_user_id}
                                            onChange={(e) => setCoupangForm({ ...coupangForm, vendor_user_id: e.target.value })}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">Access Key</label>
                                        <Input
                                            type="password"
                                            value={coupangForm.access_key}
                                            onChange={(e) => setCoupangForm({ ...coupangForm, access_key: e.target.value })}
                                            size="sm"
                                            placeholder={coupangEditId ? "변경 시에만 입력" : ""}
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">Secret Key</label>
                                        <Input
                                            type="password"
                                            value={coupangForm.secret_key}
                                            onChange={(e) => setCoupangForm({ ...coupangForm, secret_key: e.target.value })}
                                            size="sm"
                                            placeholder={coupangEditId ? "변경 시에만 입력" : ""}
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">상태</label>
                                        <Select
                                            value={coupangForm.is_active ? "active" : "inactive"}
                                            onValueChange={(value) => setCoupangForm({ ...coupangForm, is_active: value === "active" })}
                                            options={[
                                                { value: "active", label: "Active" },
                                                { value: "inactive", label: "Inactive" }
                                            ]}
                                            size="sm"
                                        />
                                    </div>
                                </div>
                                <div className="flex items-center justify-end gap-2">
                                    <Button variant="outline" size="sm" onClick={resetCoupangForm}>
                                        초기화
                                    </Button>
                                    <Button size="sm" onClick={handleUpsertCoupang}>
                                        <Plus className="h-3 w-3 mr-1" />
                                        {coupangEditId ? "업데이트" : "등록"}
                                    </Button>
                                </div>
                                <Table
                                    columns={coupangColumns}
                                    data={coupangAccounts}
                                    loading={marketLoading}
                                    emptyMessage="쿠팡 계정이 없습니다."
                                    compact
                                />
                            </CardContent>
                        </Card>

                        <Card className="border border-border">
                            <CardHeader className="pb-2 flex flex-row items-center justify-between">
                                <CardTitle className="text-xs flex items-center gap-1">
                                    <Settings className="h-3 w-3 text-primary" />
                                    스마트스토어 계정
                                </CardTitle>
                                <Button variant="outline" size="xs" onClick={loadMarketAccounts}>
                                    <RefreshCw className="h-3 w-3 mr-1" />
                                    새로고침
                                </Button>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                <div className="grid gap-2 md:grid-cols-3">
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">계정 이름</label>
                                        <Input
                                            value={smartstoreForm.name}
                                            onChange={(e) => setSmartstoreForm({ ...smartstoreForm, name: e.target.value })}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">Client ID</label>
                                        <Input
                                            value={smartstoreForm.client_id}
                                            onChange={(e) => setSmartstoreForm({ ...smartstoreForm, client_id: e.target.value })}
                                            size="sm"
                                            placeholder={smartstoreEditId ? "변경 시에만 입력" : ""}
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">Client Secret</label>
                                        <Input
                                            type="password"
                                            value={smartstoreForm.client_secret}
                                            onChange={(e) => setSmartstoreForm({ ...smartstoreForm, client_secret: e.target.value })}
                                            size="sm"
                                            placeholder={smartstoreEditId ? "변경 시에만 입력" : ""}
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">상태</label>
                                        <Select
                                            value={smartstoreForm.is_active ? "active" : "inactive"}
                                            onValueChange={(value) => setSmartstoreForm({ ...smartstoreForm, is_active: value === "active" })}
                                            options={[
                                                { value: "active", label: "Active" },
                                                { value: "inactive", label: "Inactive" }
                                            ]}
                                            size="sm"
                                        />
                                    </div>
                                </div>
                                <div className="flex items-center justify-end gap-2">
                                    <Button variant="outline" size="sm" onClick={resetSmartstoreForm}>
                                        초기화
                                    </Button>
                                    <Button size="sm" onClick={handleUpsertSmartstore}>
                                        <Plus className="h-3 w-3 mr-1" />
                                        {smartstoreEditId ? "업데이트" : "등록"}
                                    </Button>
                                </div>
                                <Table
                                    columns={smartstoreColumns}
                                    data={smartstoreAccounts}
                                    loading={marketLoading}
                                    emptyMessage="스마트스토어 계정이 없습니다."
                                    compact
                                />
                            </CardContent>
                        </Card>
                    </div>
                )}

                {activeTab === "supplier" && (
                    <div className="space-y-3">
                        <Card className="border border-border">
                            <CardHeader className="pb-2 flex flex-row items-center justify-between">
                                <CardTitle className="text-xs flex items-center gap-1">
                                    <Settings className="h-3 w-3 text-primary" />
                                    오너클랜 계정
                                </CardTitle>
                                <Button variant="outline" size="xs" onClick={loadSupplierData}>
                                    <RefreshCw className="h-3 w-3 mr-1" />
                                    새로고침
                                </Button>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                {ownerclanPrimary ? (
                                    <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                                        <Badge variant="primary">PRIMARY</Badge>
                                        <span>{ownerclanPrimary.username}</span>
                                        <span className="text-[9px]">({ownerclanPrimary.userType})</span>
                                    </div>
                                ) : (
                                    <div className="text-[10px] text-muted-foreground">대표 계정이 설정되어 있지 않습니다.</div>
                                )}

                                <div className="grid gap-2 md:grid-cols-3">
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">유형</label>
                                        <Select
                                            value={ownerclanForm.user_type}
                                            onValueChange={(value) => setOwnerclanForm({ ...ownerclanForm, user_type: value })}
                                            options={[
                                                { value: "seller", label: "seller" },
                                                { value: "vendor", label: "vendor" },
                                                { value: "supplier", label: "supplier" }
                                            ]}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">아이디</label>
                                        <Input
                                            value={ownerclanForm.username}
                                            onChange={(e) => setOwnerclanForm({ ...ownerclanForm, username: e.target.value })}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">비밀번호</label>
                                        <Input
                                            type="password"
                                            value={ownerclanForm.password}
                                            onChange={(e) => setOwnerclanForm({ ...ownerclanForm, password: e.target.value })}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">대표 계정</label>
                                        <Select
                                            value={ownerclanForm.set_primary ? "yes" : "no"}
                                            onValueChange={(value) => setOwnerclanForm({ ...ownerclanForm, set_primary: value === "yes" })}
                                            options={[
                                                { value: "yes", label: "Primary" },
                                                { value: "no", label: "Secondary" }
                                            ]}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">상태</label>
                                        <Select
                                            value={ownerclanForm.is_active ? "active" : "inactive"}
                                            onValueChange={(value) => setOwnerclanForm({ ...ownerclanForm, is_active: value === "active" })}
                                            options={[
                                                { value: "active", label: "Active" },
                                                { value: "inactive", label: "Inactive" }
                                            ]}
                                            size="sm"
                                        />
                                    </div>
                                </div>
                                <div className="flex items-center justify-end gap-2">
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => setOwnerclanForm({
                                            user_type: "seller",
                                            username: "",
                                            password: "",
                                            set_primary: true,
                                            is_active: true
                                        })}
                                    >
                                        초기화
                                    </Button>
                                    <Button size="sm" onClick={handleUpsertOwnerclan} isLoading={ownerclanSubmitting}>
                                        <Plus className="h-3 w-3 mr-1" />
                                        저장
                                    </Button>
                                </div>
                                <Table
                                    columns={ownerclanColumns}
                                    data={ownerclanAccounts}
                                    loading={supplierLoading}
                                    emptyMessage="오너클랜 계정이 없습니다."
                                    compact
                                />
                            </CardContent>
                        </Card>

                        <Card className="border border-border">
                            <CardHeader className="pb-2 flex flex-row items-center justify-between">
                                <CardTitle className="text-xs flex items-center gap-1">
                                    <Settings className="h-3 w-3 text-primary" />
                                    오너클랜 동기화
                                </CardTitle>
                                <Button variant="outline" size="xs" onClick={loadSupplierData}>
                                    <RefreshCw className="h-3 w-3 mr-1" />
                                    새로고침
                                </Button>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                <div className="flex flex-wrap gap-2">
                                    <Button size="xs" variant="outline" onClick={() => triggerOwnerclanSync("items")}>
                                        상품 동기화
                                    </Button>
                                    <Button size="xs" variant="outline" onClick={() => triggerOwnerclanSync("orders")}>
                                        주문 동기화
                                    </Button>
                                    <Button size="xs" variant="outline" onClick={() => triggerOwnerclanSync("qna")}>
                                        문의 동기화
                                    </Button>
                                    <Button size="xs" variant="outline" onClick={() => triggerOwnerclanSync("categories")}>
                                        카테고리 동기화
                                    </Button>
                                </div>
                                <Table
                                    columns={syncJobColumns}
                                    data={syncJobs}
                                    loading={supplierLoading}
                                    emptyMessage="최근 동기화 작업이 없습니다."
                                    compact
                                />
                            </CardContent>
                        </Card>
                    </div>
                )}

                {activeTab === "ai" && (
                    <div className="space-y-3">
                        <Card className="border border-border">
                            <CardHeader className="pb-2 flex flex-row items-center justify-between">
                                <CardTitle className="text-xs flex items-center gap-1">
                                    <KeyRound className="h-3 w-3 text-primary" />
                                    AI 키 관리
                                </CardTitle>
                                <Button variant="outline" size="xs" onClick={loadAIKeys}>
                                    <RefreshCw className="h-3 w-3 mr-1" />
                                    새로고침
                                </Button>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                <div className="grid gap-2 md:grid-cols-3">
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">Provider</label>
                                        <Select
                                            value={aiForm.provider}
                                            onValueChange={(value) => setAiForm({ ...aiForm, provider: value })}
                                            options={[
                                                { value: "openai", label: "OpenAI" },
                                                { value: "gemini", label: "Gemini" }
                                            ]}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1 md:col-span-2">
                                        <label className="text-[10px] font-medium text-muted-foreground">API Key</label>
                                        <Input
                                            type="password"
                                            value={aiForm.key}
                                            onChange={(e) => setAiForm({ ...aiForm, key: e.target.value })}
                                            size="sm"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label className="text-[10px] font-medium text-muted-foreground">상태</label>
                                        <Select
                                            value={aiForm.is_active ? "active" : "inactive"}
                                            onValueChange={(value) => setAiForm({ ...aiForm, is_active: value === "active" })}
                                            options={[
                                                { value: "active", label: "Active" },
                                                { value: "inactive", label: "Inactive" }
                                            ]}
                                            size="sm"
                                        />
                                    </div>
                                </div>
                                <div className="flex items-center justify-end gap-2">
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => setAiForm({ provider: "openai", key: "", is_active: true })}
                                    >
                                        초기화
                                    </Button>
                                    <Button size="sm" onClick={handleCreateAIKey}>
                                        <Plus className="h-3 w-3 mr-1" />
                                        등록
                                    </Button>
                                </div>
                                <Table
                                    columns={aiColumns}
                                    data={aiKeys}
                                    loading={aiLoading}
                                    emptyMessage="등록된 AI 키가 없습니다."
                                    compact
                                />
                            </CardContent>
                        </Card>
                    </div>
                )}
            </div>
        </div>
    );
}
