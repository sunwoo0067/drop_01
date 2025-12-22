'use client';

import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { Search, X } from "lucide-react";

interface FiltersProps {
    filters: any;
    setFilters: (filters: any) => void;
    onSearch: () => void;
    isLoading?: boolean;
}

export default function BenchmarkFilters({ filters, setFilters, onSearch, isLoading }: FiltersProps) {
    const handleChange = (key: string, value: any) => {
        setFilters({ ...filters, [key]: value });
    };

    const clearFilters = () => {
        setFilters({
            q: "",
            marketCode: "ALL",
            minPrice: "",
            maxPrice: "",
            minReviewCount: "",
            minRating: "",
            minQualityScore: "",
            orderBy: "created"
        });
    };

    return (
        <div className="space-y-6 p-4">
            <div>
                <h3 className="text-sm font-semibold mb-3">검색 및 필터</h3>
                <div className="relative">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                        className="pl-9"
                        placeholder="상품명 검색..."
                        value={filters.q}
                        onChange={(e) => handleChange("q", e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && onSearch()}
                    />
                </div>
            </div>

            <div className="space-y-4">
                <Select
                    label="마켓"
                    options={[
                        { value: "ALL", label: "전체" },
                        { value: "COUPANG", label: "쿠팡" },
                        { value: "NAVER_SHOPPING", label: "네이버쇼핑" },
                        { value: "GMARKET", label: "G마켓" },
                        { value: "AUCTION", label: "옥션" },
                        { value: "ELEVENST", label: "11번가" },
                    ]}
                    value={filters.marketCode}
                    onChange={(e) => handleChange("marketCode", e.target.value)}
                />

                <div className="grid grid-cols-2 gap-2">
                    <div>
                        <label className="text-xs font-medium text-muted-foreground mb-1 block">최소 가격</label>
                        <Input
                            type="number"
                            placeholder="0"
                            value={filters.minPrice}
                            onChange={(e) => handleChange("minPrice", e.target.value)}
                        />
                    </div>
                    <div>
                        <label className="text-xs font-medium text-muted-foreground mb-1 block">최대 가격</label>
                        <Input
                            type="number"
                            placeholder="무제한"
                            value={filters.maxPrice}
                            onChange={(e) => handleChange("maxPrice", e.target.value)}
                        />
                    </div>
                </div>

                <div>
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">최소 리뷰 수</label>
                    <Input
                        type="number"
                        placeholder="0"
                        value={filters.minReviewCount}
                        onChange={(e) => handleChange("minReviewCount", e.target.value)}
                    />
                </div>

                <div>
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">최소 평점 (0-5)</label>
                    <Input
                        type="number"
                        step="0.1"
                        min="0"
                        max="5"
                        placeholder="0.0"
                        value={filters.minRating}
                        onChange={(e) => handleChange("minRating", e.target.value)}
                    />
                </div>

                <div>
                    <label className="text-xs font-medium text-muted-foreground mb-1 block">최소 품질 점수 (0-10)</label>
                    <Input
                        type="number"
                        step="0.1"
                        min="0"
                        max="10"
                        placeholder="0.0"
                        value={filters.minQualityScore}
                        onChange={(e) => handleChange("minQualityScore", e.target.value)}
                    />
                </div>

                <Select
                    label="정렬"
                    options={[
                        { value: "created", label: "최신순" },
                        { value: "updated", label: "업데이트순" },
                        { value: "price_asc", label: "가격 낮은순" },
                        { value: "price_desc", label: "가격 높은순" },
                        { value: "reviews", label: "리뷰 많은순" },
                        { value: "rating", label: "평점 높은순" },
                        { value: "quality", label: "품질 점수순" },
                    ]}
                    value={filters.orderBy}
                    onChange={(e) => handleChange("orderBy", e.target.value)}
                />
            </div>

            <div className="pt-4 flex flex-col gap-2">
                <Button onClick={onSearch} className="w-full" disabled={isLoading}>
                    필터 적용
                </Button>
                <Button variant="ghost" onClick={clearFilters} className="w-full text-xs text-muted-foreground">
                    <X className="h-3 w-3 mr-1" />
                    필터 초기화
                </Button>
            </div>
        </div>
    );
}
