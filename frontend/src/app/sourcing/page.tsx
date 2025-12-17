"use client";

import { useEffect, useState } from "react";
import { Search, Filter, Plus } from "lucide-react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import api from "@/lib/api";
import { SourcingCandidate } from "@/types";

export default function SourcingPage() {
    const [searchTerm, setSearchTerm] = useState("");
    const [items, setItems] = useState<SourcingCandidate[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchCandidates = async (q?: string) => {
        setLoading(true);
        setError(null);
        try {
            const response = await api.get("/sourcing/candidates", {
                params: {
                    q: (q ?? "").trim() || undefined,
                    limit: 50,
                    offset: 0,
                },
            });
            setItems(Array.isArray(response.data) ? response.data : []);
        } catch (e) {
            console.error("Failed to fetch sourcing candidates", e);
            setError("소싱 후보 목록을 불러오지 못했습니다.");
            setItems([]);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchCandidates();
    }, []);

    const handleSearch = async () => {
        await fetchCandidates(searchTerm);
    };

    return (
        <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <h1 className="text-3xl font-bold tracking-tight">상품 소싱</h1>
                <div className="flex items-center gap-2">
                    <Button variant="outline">
                        <Filter className="mr-2 h-4 w-4" />
                        필터
                    </Button>
                    <Button>
                        <Plus className="mr-2 h-4 w-4" />
                        새 소싱 작업
                    </Button>
                </div>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>상품 검색</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex gap-4">
                        <Input
                            placeholder="키워드 또는 상품 ID 검색..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="max-w-md"
                        />
                        <Button onClick={handleSearch} disabled={loading}>
                            <Search className="mr-2 h-4 w-4" />
                            검색
                        </Button>
                    </div>
                </CardContent>
            </Card>

            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-6">
                {loading ? (
                    <div className="col-span-full h-40 flex items-center justify-center">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                ) : error ? (
                    <div className="col-span-full h-40 flex items-center justify-center text-muted-foreground">
                        {error}
                    </div>
                ) : items.length === 0 ? (
                    <div className="col-span-full h-40 flex items-center justify-center text-muted-foreground">
                        소싱 후보가 없습니다.
                    </div>
                ) : (
                    items.map((item) => (
                        <Card key={item.id} className="overflow-hidden">
                            <div className="aspect-square bg-muted flex items-center justify-center text-muted-foreground relative">
                                <span className="text-sm">No Image</span>
                                <Badge className="absolute top-2 right-2" variant="secondary">{item.supplierCode}</Badge>
                            </div>
                            <CardContent className="p-4 space-y-1">
                                <h3 className="font-semibold truncate">{item.name}</h3>
                                <p className="text-sm text-muted-foreground">공급가 {item.supplyPrice?.toLocaleString()} 원</p>
                                <div className="flex flex-wrap gap-1 pt-1">
                                    <Badge variant="outline">{item.sourceStrategy}</Badge>
                                    <Badge variant="secondary">{item.status}</Badge>
                                </div>
                            </CardContent>
                            <CardFooter className="p-4 pt-0">
                                <Button className="w-full" variant="outline" size="sm" disabled>
                                    상세 보기
                                </Button>
                            </CardFooter>
                        </Card>
                    ))
                )}
            </div>
        </div>
    );
}
