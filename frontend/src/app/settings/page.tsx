"use client";

import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import api from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";

type SettingsTab = "supplier" | "market" | "ai";

type OwnerClanStatus = {
    configured: boolean;
    account: null | {
        id: string;
        supplierCode: string;
        userType: string;
        username: string;
        tokenExpiresAt: string | null;
        isPrimary: boolean;
        isActive: boolean;
        updatedAt: string | null;
    };
};

type CoupangAccount = {
    id: string;
    marketCode: string;
    name: string;
    isActive: boolean;
    vendorId: string;
    vendorUserId: string;
    accessKeyMasked: string | null;
    secretKeyMasked: string | null;
    createdAt: string | null;
    updatedAt: string | null;
};

type AIKey = {
    id: string;
    provider: "openai" | "gemini";
    keyMasked: string | null;
    isActive: boolean;
    createdAt: string | null;
};

function formatDateTime(value: string | null | undefined): string {
    if (!value) return "-";
    try {
        return new Date(value).toLocaleString("ko-KR");
    } catch {
        return value;
    }
}

function getErrorMessage(error: unknown): string {
    if (axios.isAxiosError(error)) {
        const detail = (error.response?.data as any)?.detail;
        if (typeof detail === "string" && detail) return detail;
        return error.message;
    }

    if (error instanceof Error) return error.message;
    return "알 수 없는 오류가 발생했습니다.";
}

export default function SettingsPage() {
    const [tab, setTab] = useState<SettingsTab>("supplier");

    const [ownerClanStatus, setOwnerClanStatus] = useState<OwnerClanStatus | null>(null);
    const [ownerClanLoading, setOwnerClanLoading] = useState(false);
    const [ownerClanForm, setOwnerClanForm] = useState({
        userType: "seller",
        username: "",
        password: "",
    });

    const [coupangLoading, setCoupangLoading] = useState(false);
    const [coupangAccounts, setCoupangAccounts] = useState<CoupangAccount[]>([]);
    const [coupangCreateForm, setCoupangCreateForm] = useState({
        name: "",
        vendorId: "",
        vendorUserId: "",
        accessKey: "",
        secretKey: "",
        activate: false,
    });
    const [editingCoupangId, setEditingCoupangId] = useState<string | null>(null);
    const [coupangEditForm, setCoupangEditForm] = useState({
        name: "",
        vendorId: "",
        vendorUserId: "",
        accessKey: "",
        secretKey: "",
        activate: false,
    });
    const [coupangEditLoading, setCoupangEditLoading] = useState(false);

    const [aiLoading, setAiLoading] = useState(false);
    const [aiKeys, setAiKeys] = useState<AIKey[]>([]);
    const [aiCreateLoading, setAiCreateLoading] = useState(false);
    const [aiCreateForm, setAiCreateForm] = useState({
        provider: "openai" as "openai" | "gemini",
        key: "",
        isActive: true,
    });

    const tabButtons = useMemo(
        () => [
            { id: "supplier" as const, label: "공급사" },
            { id: "market" as const, label: "마켓" },
            { id: "ai" as const, label: "AI 키" },
        ],
        []
    );

    const fetchOwnerClanStatus = async () => {
        setOwnerClanLoading(true);
        try {
            const res = await api.get<OwnerClanStatus>("/settings/suppliers/ownerclan/primary");
            setOwnerClanStatus(res.data);
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setOwnerClanLoading(false);
        }
    };

    const fetchCoupangAccounts = async () => {
        setCoupangLoading(true);
        try {
            const res = await api.get<CoupangAccount[]>("/settings/markets/coupang/accounts");
            setCoupangAccounts(res.data);
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setCoupangLoading(false);
        }
    };

    const fetchAIKeys = async () => {
        setAiLoading(true);
        try {
            const res = await api.get<AIKey[]>("/settings/ai/keys");
            setAiKeys(res.data);
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setAiLoading(false);
        }
    };

    useEffect(() => {
        fetchOwnerClanStatus();
        fetchCoupangAccounts();
        fetchAIKeys();
    }, []);

    const handleOwnerClanSave = async () => {
        if (!ownerClanForm.username || !ownerClanForm.password) {
            alert("오너클랜 ID/PW를 입력해 주세요.");
            return;
        }

        setOwnerClanLoading(true);
        try {
            await api.post("/settings/suppliers/ownerclan/primary", {
                user_type: ownerClanForm.userType,
                username: ownerClanForm.username,
                password: ownerClanForm.password,
            });
            setOwnerClanForm((prev) => ({ ...prev, password: "" }));
            await fetchOwnerClanStatus();
            alert("오너클랜 대표 계정이 설정되었습니다.");
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setOwnerClanLoading(false);
        }
    };

    const handleCreateCoupangAccount = async () => {
        if (!coupangCreateForm.name || !coupangCreateForm.vendorId || !coupangCreateForm.accessKey || !coupangCreateForm.secretKey) {
            alert("계정 이름, vendorId, Access Key, Secret Key는 필수입니다.");
            return;
        }

        setCoupangLoading(true);
        try {
            await api.post("/settings/markets/coupang/accounts", {
                name: coupangCreateForm.name,
                vendor_id: coupangCreateForm.vendorId,
                vendor_user_id: coupangCreateForm.vendorUserId,
                access_key: coupangCreateForm.accessKey,
                secret_key: coupangCreateForm.secretKey,
                is_active: coupangCreateForm.activate,
            });
            setCoupangCreateForm({ name: "", vendorId: "", vendorUserId: "", accessKey: "", secretKey: "", activate: false });
            await fetchCoupangAccounts();
            alert("쿠팡 계정이 추가되었습니다.");
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setCoupangLoading(false);
        }
    };

    const handleActivateCoupang = async (id: string) => {
        if (!confirm("이 계정을 활성화하시겠습니까? (기존 활성 계정은 비활성 처리됩니다)")) return;

        setCoupangLoading(true);
        try {
            await api.post(`/settings/markets/coupang/accounts/${id}/activate`);
            await fetchCoupangAccounts();
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setCoupangLoading(false);
        }
    };

    const startEditCoupang = (account: CoupangAccount) => {
        setEditingCoupangId(account.id);
        setCoupangEditForm({
            name: account.name,
            vendorId: account.vendorId,
            vendorUserId: account.vendorUserId,
            accessKey: "",
            secretKey: "",
            activate: account.isActive,
        });
    };

    const cancelEditCoupang = () => {
        setEditingCoupangId(null);
        setCoupangEditForm({ name: "", vendorId: "", vendorUserId: "", accessKey: "", secretKey: "", activate: false });
    };

    const saveEditCoupang = async () => {
        if (!editingCoupangId) return;
        if (!coupangEditForm.name || !coupangEditForm.vendorId) {
            alert("계정 이름과 vendorId는 필수입니다.");
            return;
        }

        setCoupangEditLoading(true);
        try {
            const payload: any = {
                name: coupangEditForm.name,
                vendor_id: coupangEditForm.vendorId,
                vendor_user_id: coupangEditForm.vendorUserId,
                is_active: coupangEditForm.activate,
            };
            if (coupangEditForm.accessKey) payload.access_key = coupangEditForm.accessKey;
            if (coupangEditForm.secretKey) payload.secret_key = coupangEditForm.secretKey;

            await api.patch(`/settings/markets/coupang/accounts/${editingCoupangId}`, payload);
            cancelEditCoupang();
            await fetchCoupangAccounts();
            alert("쿠팡 계정 정보가 수정되었습니다.");
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setCoupangEditLoading(false);
        }
    };

    const handleCreateAIKey = async () => {
        if (!aiCreateForm.key) {
            alert("API Key를 입력해 주세요.");
            return;
        }

        setAiCreateLoading(true);
        try {
            await api.post("/settings/ai/keys", {
                provider: aiCreateForm.provider,
                key: aiCreateForm.key,
                is_active: aiCreateForm.isActive,
            });
            setAiCreateForm((prev) => ({ ...prev, key: "" }));
            await fetchAIKeys();
            alert("AI Key가 추가되었습니다.");
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setAiCreateLoading(false);
        }
    };

    const toggleAIKeyActive = async (key: AIKey) => {
        setAiLoading(true);
        try {
            await api.patch(`/settings/ai/keys/${key.id}`, { is_active: !key.isActive });
            await fetchAIKeys();
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setAiLoading(false);
        }
    };

    const deleteAIKey = async (key: AIKey) => {
        if (!confirm("이 API Key를 삭제하시겠습니까?")) return;

        setAiLoading(true);
        try {
            await api.delete(`/settings/ai/keys/${key.id}`);
            await fetchAIKeys();
        } catch (e) {
            console.error(e);
            alert(getErrorMessage(e));
        } finally {
            setAiLoading(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex flex-col gap-4">
                <h1 className="text-3xl font-bold tracking-tight">설정</h1>
                <div className="flex flex-wrap gap-2">
                    {tabButtons.map((b) => (
                        <Button
                            key={b.id}
                            variant={tab === b.id ? "primary" : "outline"}
                            onClick={() => setTab(b.id)}
                        >
                            {b.label}
                        </Button>
                    ))}
                    <Button
                        variant="ghost"
                        onClick={() => {
                            fetchOwnerClanStatus();
                            fetchCoupangAccounts();
                            fetchAIKeys();
                        }}
                    >
                        새로고침
                    </Button>
                </div>
            </div>

            {tab === "supplier" && (
                <div className="space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>오너클랜 대표 계정 상태</CardTitle>
                        </CardHeader>
                        <CardContent>
                            {ownerClanLoading && !ownerClanStatus ? (
                                <div className="text-sm text-muted-foreground">불러오는 중...</div>
                            ) : ownerClanStatus?.configured && ownerClanStatus.account ? (
                                <div className="space-y-2">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <Badge variant="success">설정됨</Badge>
                                        {ownerClanStatus.account.isActive ? <Badge variant="secondary">활성</Badge> : <Badge variant="outline">비활성</Badge>}
                                    </div>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <div className="text-sm">
                                            <div className="text-muted-foreground">아이디</div>
                                            <div className="font-medium">{ownerClanStatus.account.username}</div>
                                        </div>
                                        <div className="text-sm">
                                            <div className="text-muted-foreground">유형</div>
                                            <div className="font-medium">{ownerClanStatus.account.userType}</div>
                                        </div>
                                        <div className="text-sm">
                                            <div className="text-muted-foreground">토큰 만료</div>
                                            <div className="font-medium">{formatDateTime(ownerClanStatus.account.tokenExpiresAt)}</div>
                                        </div>
                                        <div className="text-sm">
                                            <div className="text-muted-foreground">업데이트</div>
                                            <div className="font-medium">{formatDateTime(ownerClanStatus.account.updatedAt)}</div>
                                        </div>
                                    </div>
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    <Badge variant="warning">미설정</Badge>
                                    <div className="text-sm text-muted-foreground">오너클랜 대표 계정을 설정해 주세요.</div>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>오너클랜 대표 계정 설정</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div className="space-y-1">
                                    <div className="text-sm font-medium">유형</div>
                                    <select
                                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        value={ownerClanForm.userType}
                                        onChange={(e) => setOwnerClanForm((prev) => ({ ...prev, userType: e.target.value }))}
                                    >
                                        <option value="seller">seller</option>
                                    </select>
                                </div>
                                <div className="space-y-1">
                                    <div className="text-sm font-medium">아이디</div>
                                    <Input
                                        value={ownerClanForm.username}
                                        onChange={(e) => setOwnerClanForm((prev) => ({ ...prev, username: e.target.value }))}
                                        placeholder="오너클랜 아이디"
                                    />
                                </div>
                                <div className="space-y-1">
                                    <div className="text-sm font-medium">비밀번호</div>
                                    <Input
                                        type="password"
                                        value={ownerClanForm.password}
                                        onChange={(e) => setOwnerClanForm((prev) => ({ ...prev, password: e.target.value }))}
                                        placeholder="오너클랜 비밀번호"
                                    />
                                </div>
                            </div>
                        </CardContent>
                        <CardFooter className="flex justify-end">
                            <Button onClick={handleOwnerClanSave} isLoading={ownerClanLoading}>
                                저장
                            </Button>
                        </CardFooter>
                    </Card>
                </div>
            )}

            {tab === "market" && (
                <div className="space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>쿠팡 계정 추가</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="space-y-1">
                                    <div className="text-sm font-medium">계정 이름</div>
                                    <Input
                                        value={coupangCreateForm.name}
                                        onChange={(e) => setCoupangCreateForm((prev) => ({ ...prev, name: e.target.value }))}
                                        placeholder="예: 메인 계정"
                                    />
                                </div>
                                <div className="space-y-1">
                                    <div className="text-sm font-medium">vendorId</div>
                                    <Input
                                        value={coupangCreateForm.vendorId}
                                        onChange={(e) => setCoupangCreateForm((prev) => ({ ...prev, vendorId: e.target.value }))}
                                        placeholder="예: A00012345"
                                    />
                                </div>
                                <div className="space-y-1">
                                    <div className="text-sm font-medium">vendorUserId (Wing ID)</div>
                                    <Input
                                        value={coupangCreateForm.vendorUserId}
                                        onChange={(e) => setCoupangCreateForm((prev) => ({ ...prev, vendorUserId: e.target.value }))}
                                        placeholder="선택"
                                    />
                                </div>
                                <div className="space-y-1">
                                    <div className="text-sm font-medium">Access Key</div>
                                    <Input
                                        type="password"
                                        value={coupangCreateForm.accessKey}
                                        onChange={(e) => setCoupangCreateForm((prev) => ({ ...prev, accessKey: e.target.value }))}
                                        placeholder="쿠팡 Access Key"
                                    />
                                </div>
                                <div className="space-y-1">
                                    <div className="text-sm font-medium">Secret Key</div>
                                    <Input
                                        type="password"
                                        value={coupangCreateForm.secretKey}
                                        onChange={(e) => setCoupangCreateForm((prev) => ({ ...prev, secretKey: e.target.value }))}
                                        placeholder="쿠팡 Secret Key"
                                    />
                                </div>
                                <div className="flex items-end">
                                    <label className="flex items-center gap-2 text-sm">
                                        <input
                                            type="checkbox"
                                            checked={coupangCreateForm.activate}
                                            onChange={(e) => setCoupangCreateForm((prev) => ({ ...prev, activate: e.target.checked }))}
                                        />
                                        이 계정을 활성화
                                    </label>
                                </div>
                            </div>
                        </CardContent>
                        <CardFooter className="flex justify-end">
                            <Button onClick={handleCreateCoupangAccount} isLoading={coupangLoading}>
                                추가
                            </Button>
                        </CardFooter>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>쿠팡 계정 목록</CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                            <div className="overflow-x-auto">
                                <table className="w-full caption-bottom text-sm text-left">
                                    <thead className="[&_tr]:border-b">
                                        <tr className="border-b">
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground">이름</th>
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground">vendorId</th>
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground">vendorUserId</th>
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground">Access Key</th>
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground">Secret Key</th>
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground">상태</th>
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground text-right">작업</th>
                                        </tr>
                                    </thead>
                                    <tbody className="[&_tr:last-child]:border-0">
                                        {coupangLoading && coupangAccounts.length === 0 ? (
                                            <tr>
                                                <td colSpan={7} className="h-24 text-center text-muted-foreground">불러오는 중...</td>
                                            </tr>
                                        ) : coupangAccounts.length === 0 ? (
                                            <tr>
                                                <td colSpan={7} className="h-24 text-center text-muted-foreground">등록된 쿠팡 계정이 없습니다.</td>
                                            </tr>
                                        ) : (
                                            coupangAccounts.map((account) => (
                                                <tr key={account.id} className="border-b transition-colors hover:bg-muted/50">
                                                    <td className="p-4 align-middle">
                                                        {editingCoupangId === account.id ? (
                                                            <Input
                                                                value={coupangEditForm.name}
                                                                onChange={(e) => setCoupangEditForm((prev) => ({ ...prev, name: e.target.value }))}
                                                            />
                                                        ) : (
                                                            <div className="font-medium">{account.name}</div>
                                                        )}
                                                    </td>
                                                    <td className="p-4 align-middle">
                                                        {editingCoupangId === account.id ? (
                                                            <Input
                                                                value={coupangEditForm.vendorId}
                                                                onChange={(e) => setCoupangEditForm((prev) => ({ ...prev, vendorId: e.target.value }))}
                                                            />
                                                        ) : (
                                                            account.vendorId
                                                        )}
                                                    </td>
                                                    <td className="p-4 align-middle">
                                                        {editingCoupangId === account.id ? (
                                                            <Input
                                                                value={coupangEditForm.vendorUserId}
                                                                onChange={(e) => setCoupangEditForm((prev) => ({ ...prev, vendorUserId: e.target.value }))}
                                                            />
                                                        ) : (
                                                            account.vendorUserId || "-"
                                                        )}
                                                    </td>
                                                    <td className="p-4 align-middle">
                                                        {editingCoupangId === account.id ? (
                                                            <Input
                                                                type="password"
                                                                value={coupangEditForm.accessKey}
                                                                onChange={(e) => setCoupangEditForm((prev) => ({ ...prev, accessKey: e.target.value }))}
                                                                placeholder="변경 시에만 입력"
                                                            />
                                                        ) : (
                                                            account.accessKeyMasked || "-"
                                                        )}
                                                    </td>
                                                    <td className="p-4 align-middle">
                                                        {editingCoupangId === account.id ? (
                                                            <Input
                                                                type="password"
                                                                value={coupangEditForm.secretKey}
                                                                onChange={(e) => setCoupangEditForm((prev) => ({ ...prev, secretKey: e.target.value }))}
                                                                placeholder="변경 시에만 입력"
                                                            />
                                                        ) : (
                                                            account.secretKeyMasked || "-"
                                                        )}
                                                    </td>
                                                    <td className="p-4 align-middle">
                                                        {editingCoupangId === account.id ? (
                                                            <label className="flex items-center gap-2 text-sm">
                                                                <input
                                                                    type="checkbox"
                                                                    checked={coupangEditForm.activate}
                                                                    onChange={(e) => setCoupangEditForm((prev) => ({ ...prev, activate: e.target.checked }))}
                                                                />
                                                                활성
                                                            </label>
                                                        ) : account.isActive ? (
                                                            <Badge variant="success">활성</Badge>
                                                        ) : (
                                                            <Badge variant="secondary">비활성</Badge>
                                                        )}
                                                    </td>
                                                    <td className="p-4 align-middle text-right">
                                                        <div className="flex justify-end gap-2">
                                                            {editingCoupangId === account.id ? (
                                                                <>
                                                                    <Button
                                                                        size="sm"
                                                                        isLoading={coupangEditLoading}
                                                                        onClick={saveEditCoupang}
                                                                    >
                                                                        저장
                                                                    </Button>
                                                                    <Button size="sm" variant="outline" onClick={cancelEditCoupang}>
                                                                        취소
                                                                    </Button>
                                                                </>
                                                            ) : (
                                                                <>
                                                                    {!account.isActive && (
                                                                        <Button
                                                                            size="sm"
                                                                            variant="outline"
                                                                            disabled={coupangLoading}
                                                                            onClick={() => handleActivateCoupang(account.id)}
                                                                        >
                                                                            활성화
                                                                        </Button>
                                                                    )}
                                                                    <Button size="sm" variant="ghost" onClick={() => startEditCoupang(account)}>
                                                                        수정
                                                                    </Button>
                                                                </>
                                                            )}
                                                        </div>
                                                    </td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            )}

            {tab === "ai" && (
                <div className="space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>AI API Key 추가</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div className="space-y-1">
                                    <div className="text-sm font-medium">Provider</div>
                                    <select
                                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        value={aiCreateForm.provider}
                                        onChange={(e) => setAiCreateForm((prev) => ({ ...prev, provider: e.target.value as any }))}
                                    >
                                        <option value="openai">openai</option>
                                        <option value="gemini">gemini</option>
                                    </select>
                                </div>
                                <div className="space-y-1 md:col-span-2">
                                    <div className="text-sm font-medium">API Key</div>
                                    <Input
                                        type="password"
                                        value={aiCreateForm.key}
                                        onChange={(e) => setAiCreateForm((prev) => ({ ...prev, key: e.target.value }))}
                                        placeholder="API Key"
                                    />
                                </div>
                                <div className="flex items-end">
                                    <label className="flex items-center gap-2 text-sm">
                                        <input
                                            type="checkbox"
                                            checked={aiCreateForm.isActive}
                                            onChange={(e) => setAiCreateForm((prev) => ({ ...prev, isActive: e.target.checked }))}
                                        />
                                        활성
                                    </label>
                                </div>
                            </div>
                        </CardContent>
                        <CardFooter className="flex justify-end">
                            <Button onClick={handleCreateAIKey} isLoading={aiCreateLoading}>
                                추가
                            </Button>
                        </CardFooter>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>AI API Key 목록</CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                            <div className="overflow-x-auto">
                                <table className="w-full caption-bottom text-sm text-left">
                                    <thead className="[&_tr]:border-b">
                                        <tr className="border-b">
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground">Provider</th>
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground">Key</th>
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground">상태</th>
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground">등록일</th>
                                            <th className="h-12 px-4 align-middle font-medium text-muted-foreground text-right">작업</th>
                                        </tr>
                                    </thead>
                                    <tbody className="[&_tr:last-child]:border-0">
                                        {aiLoading && aiKeys.length === 0 ? (
                                            <tr>
                                                <td colSpan={5} className="h-24 text-center text-muted-foreground">불러오는 중...</td>
                                            </tr>
                                        ) : aiKeys.length === 0 ? (
                                            <tr>
                                                <td colSpan={5} className="h-24 text-center text-muted-foreground">등록된 AI Key가 없습니다.</td>
                                            </tr>
                                        ) : (
                                            aiKeys.map((k) => (
                                                <tr key={k.id} className="border-b transition-colors hover:bg-muted/50">
                                                    <td className="p-4 align-middle font-medium">{k.provider}</td>
                                                    <td className="p-4 align-middle">{k.keyMasked || "-"}</td>
                                                    <td className="p-4 align-middle">
                                                        {k.isActive ? <Badge variant="success">활성</Badge> : <Badge variant="secondary">비활성</Badge>}
                                                    </td>
                                                    <td className="p-4 align-middle">{formatDateTime(k.createdAt)}</td>
                                                    <td className="p-4 align-middle text-right">
                                                        <div className="flex justify-end gap-2">
                                                            <Button
                                                                size="sm"
                                                                variant="outline"
                                                                disabled={aiLoading}
                                                                onClick={() => toggleAIKeyActive(k)}
                                                            >
                                                                {k.isActive ? "비활성화" : "활성화"}
                                                            </Button>
                                                            <Button
                                                                size="sm"
                                                                variant="danger"
                                                                disabled={aiLoading}
                                                                onClick={() => deleteAIKey(k)}
                                                            >
                                                                삭제
                                                            </Button>
                                                        </div>
                                                    </td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            )}
        </div>
    );
}
