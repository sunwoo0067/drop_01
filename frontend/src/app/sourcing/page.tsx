"use client";

import { useState } from "react";
import { Search, Filter, Plus } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

export default function SourcingPage() {
    const [searchTerm, setSearchTerm] = useState("");

    // Mock data for display
    const sourcingItems = Array.from({ length: 8 }).map((_, i) => ({
        id: i,
        name: `Sourcing Item ${i + 1}`,
        price: (i + 1) * 10000,
        source: "OwnerClan",
        image: null
    }));

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
                        <Button>
                            <Search className="mr-2 h-4 w-4" />
                            검색
                        </Button>
                    </div>
                </CardContent>
            </Card>

            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-6">
                {sourcingItems.map((item) => (
                    <Card key={item.id} className="overflow-hidden">
                        <div className="aspect-square bg-muted flex items-center justify-center text-muted-foreground relative">
                            {item.image ? (
                                <img src={item.image} alt={item.name} className="object-cover w-full h-full" />
                            ) : (
                                <span className="text-sm">No Image</span>
                            )}
                            <Badge className="absolute top-2 right-2" variant="secondary">{item.source}</Badge>
                        </div>
                        <CardContent className="p-4">
                            <h3 className="font-semibold truncate">{item.name}</h3>
                            <p className="text-sm text-muted-foreground">{item.price.toLocaleString()} 원</p>
                        </CardContent>
                        <CardFooter className="p-4 pt-0">
                            <Button className="w-full" variant="outline" size="sm">
                                상세 보기
                            </Button>
                        </CardFooter>
                    </Card>
                ))}
            </div>
        </div>
    );
}
