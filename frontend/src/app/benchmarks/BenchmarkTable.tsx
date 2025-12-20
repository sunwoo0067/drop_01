'use client';

import { BenchmarkProduct } from "@/lib/types/benchmark";
import { Badge } from "@/components/ui/Badge";
import { Star, MessageSquare, ShieldCheck, ExternalLink } from "lucide-react";

interface TableProps {
    items: BenchmarkProduct[];
    selectedId: string | null;
    onSelect: (id: string) => void;
    isLoading: boolean;
}

export default function BenchmarkTable({ items, selectedId, onSelect, isLoading }: TableProps) {
    if (isLoading && items.length === 0) {
        return (
            <div className="space-y-4 p-4">
                {[...Array(5)].map((_, i) => (
                    <div key={i} className="h-16 w-full animate-pulse bg-muted rounded-md" />
                ))}
            </div>
        );
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
                <thead className="text-xs text-muted-foreground uppercase bg-muted/50 border-y">
                    <tr>
                        <th className="px-4 py-3 font-medium">상품정보</th>
                        <th className="px-4 py-3 font-medium text-right">가격</th>
                        <th className="px-4 py-3 font-medium text-center">마켓</th>
                        <th className="px-4 py-3 font-medium text-center">평점/리뷰</th>
                        <th className="px-4 py-3 font-medium text-center">품질점수</th>
                        <th className="px-4 py-3 font-medium text-center">등록일</th>
                    </tr>
                </thead>
                <tbody className="divide-y">
                    {items.map((item) => (
                        <tr
                            key={item.id}
                            className={`hover:bg-muted/30 cursor-pointer transition-colors ${selectedId === item.id ? 'bg-primary/5 border-l-4 border-l-primary' : ''}`}
                            onClick={() => onSelect(item.id)}
                        >
                            <td className="px-4 py-3">
                                <div className="flex items-center gap-3">
                                    <div className="h-12 w-12 rounded bg-muted overflow-hidden flex-shrink-0 border">
                                        {item.imageUrls?.[0] ? (
                                            <img src={item.imageUrls[0]} alt="" className="h-full w-full object-cover" />
                                        ) : (
                                            <div className="h-full w-full flex items-center justify-center text-[8px] text-muted-foreground">No Img</div>
                                        )}
                                    </div>
                                    <div className="min-w-0">
                                        <p className="font-medium line-clamp-1" title={item.name}>{item.name}</p>
                                        <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                                            <ExternalLink className="h-3 w-3" />
                                            {item.productId}
                                        </p>
                                    </div>
                                </div>
                            </td>
                            <td className="px-4 py-3 text-right font-semibold">
                                {item.price.toLocaleString()}원
                            </td>
                            <td className="px-4 py-3 text-center">
                                <Badge variant="outline" className="text-[10px]">{item.marketCode}</Badge>
                            </td>
                            <td className="px-4 py-3 text-center">
                                <div className="flex flex-col items-center">
                                    <div className="flex items-center gap-1 text-amber-500 font-medium">
                                        <Star className="h-3 w-3 fill-current" />
                                        {item.rating?.toFixed(1) || '0.0'}
                                    </div>
                                    <div className="flex items-center gap-1 text-muted-foreground text-[10px]">
                                        <MessageSquare className="h-2.5 w-2.5" />
                                        {item.reviewCount || 0}
                                    </div>
                                </div>
                            </td>
                            <td className="px-4 py-3 text-center">
                                <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold ${(item.qualityScore || 0) >= 8 ? 'bg-green-100 text-green-700' :
                                        (item.qualityScore || 0) >= 5 ? 'bg-blue-100 text-blue-700' :
                                            'bg-gray-100 text-gray-700'
                                    }`}>
                                    <ShieldCheck className="h-3 w-3" />
                                    {item.qualityScore?.toFixed(1) || '0.0'}
                                </div>
                            </td>
                            <td className="px-4 py-3 text-center text-xs text-muted-foreground">
                                {new Date(item.createdAt || '').toLocaleDateString()}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
            {items.length === 0 && !isLoading && (
                <div className="text-center py-20 text-muted-foreground">
                    조건에 맞는 상품이 없습니다.
                </div>
            )}
        </div>
    );
}
