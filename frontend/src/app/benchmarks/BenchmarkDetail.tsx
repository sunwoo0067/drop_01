'use client';

import { useState, useEffect } from "react";
import Image from "next/image";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Loader2, ExternalLink, Star, MessageSquare, Info, ChevronRight } from "lucide-react";

interface DetailProps {
    id: string | null;
    onClose: () => void;
}

export default function BenchmarkDetail({ id, onClose }: DetailProps) {
    const [item, setItem] = useState<any>(null);
    const [isLoading, setIsLoading] = useState(false);

    const [isStartingSourcing, setIsStartingSourcing] = useState(false);

    useEffect(() => {
        if (!id) {
            setItem(null);
            return;
        }
        const fetchDetail = async () => {
            setIsLoading(true);
            try {
                const resp = await api.get(`/benchmarks/${id}`);
                setItem(resp.data);
            } catch (err) {
                console.error(err);
            } finally {
                setIsLoading(false);
            }
        };
        fetchDetail();
    }, [id]);

    const handleStartSourcing = async () => {
        if (!id || !item) return;
        setIsStartingSourcing(true);
        try {
            const resp = await api.post(`/sourcing/benchmark/${id}`);
            alert(`스마트 소싱 작업이 시작되었습니다. (Job ID: ${resp.data.jobId})\n수집 모니터 탭에서 상태를 확인할 수 있습니다.`);
        } catch (err) {
            console.error(err);
            alert("소싱 작업 시작 중 오류가 발생했습니다.");
        } finally {
            setIsStartingSourcing(false);
        }
    };

    if (!id) return null;

    return (
        <div className="h-full flex flex-col bg-background border-l shadow-xl animate-in fade-in slide-in-from-right-10 duration-300">
            <div className="flex items-center justify-between p-4 border-b bg-muted/20">
                <h3 className="font-semibold text-sm flex items-center gap-2">
                    <Info className="h-4 w-4 text-primary" />
                    상세 정보
                </h3>
                <Button variant="ghost" size="sm" onClick={onClose} className="h-8 w-8 p-0">
                    <ChevronRight className="h-4 w-4" />
                </Button>
            </div>

            <div className="flex-1 overflow-y-auto">
                {isLoading ? (
                    <div className="flex items-center justify-center h-40">
                        <Loader2 className="h-6 w-6 animate-spin text-primary" />
                    </div>
                ) : item ? (
                    <div className="p-4 space-y-6">
                        {/* ... existing content ... */}
                        <div className="space-y-4">
                            <div className="aspect-video bg-muted rounded-md overflow-hidden border relative">
                                {item.imageUrls?.[0] ? (
                                    <Image
                                        src={item.imageUrls[0]}
                                        alt={item.name || "상품 이미지"}
                                        fill
                                        sizes="(min-width: 768px) 50vw, 100vw"
                                        className="object-contain"
                                    />
                                ) : (
                                    <div className="flex items-center justify-center h-full text-muted-foreground">이미지 없음</div>
                                )}
                            </div>
                            <div className="space-y-1">
                                <div className="flex items-center gap-2">
                                    <Badge variant="outline">{item.marketCode}</Badge>
                                    <span className="text-xs text-muted-foreground">ID: {item.productId}</span>
                                </div>
                                <h2 className="font-bold text-lg leading-tight">{item.name}</h2>
                            </div>
                            <div className="flex items-baseline gap-2">
                                <span className="text-2xl font-black text-primary">{item.price.toLocaleString()}</span>
                                <span className="text-sm font-medium">원</span>
                            </div>
                        </div>

                        <div className="grid grid-cols-3 gap-2 py-4 border-y">
                            <div className="text-center">
                                <p className="text-[10px] text-muted-foreground mb-1 uppercase tracking-wider">평점</p>
                                <div className="flex items-center justify-center gap-1 text-amber-500 font-bold">
                                    <Star className="h-4 w-4 fill-current" />
                                    {item.rating?.toFixed(1) || '0.0'}
                                </div>
                            </div>
                            <div className="text-center border-x">
                                <p className="text-[10px] text-muted-foreground mb-1 uppercase tracking-wider">리뷰</p>
                                <div className="flex items-center justify-center gap-1 font-bold">
                                    <MessageSquare className="h-4 w-4 text-blue-500" />
                                    {item.reviewCount || 0}
                                </div>
                            </div>
                            <div className="text-center">
                                <p className="text-[10px] text-muted-foreground mb-1 uppercase tracking-wider">품질점수</p>
                                <div className="font-black text-primary text-base">
                                    {item.qualityScore?.toFixed(1) || '0.0'}
                                </div>
                            </div>
                        </div>

                        <div className="space-y-4 text-sm">
                            <section>
                                <h4 className="font-semibold mb-2 flex items-center gap-2">
                                    <span className="h-1 w-3 bg-primary rounded-full" />
                                    카테고리 정보
                                </h4>
                                <div className="bg-muted/30 p-3 rounded-md text-xs leading-relaxed italic border border-dashed text-muted-foreground">
                                    {item.categoryPath || '보유 정보 없음'}
                                </div>
                            </section>

                            <section>
                                <h4 className="font-semibold mb-2 flex items-center gap-2">
                                    <span className="h-1 w-3 bg-primary rounded-full" />
                                    작업 로그
                                </h4>
                                <div className="space-y-2 text-[11px] text-muted-foreground">
                                    <div className="flex justify-between">
                                        <span>수집일시</span>
                                        <span>{new Date(item.createdAt).toLocaleString()}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>최종업데이트</span>
                                        <span>{new Date(item.updatedAt).toLocaleString()}</span>
                                    </div>
                                    {item.embeddingUpdatedAt && (
                                        <div className="flex justify-between">
                                            <span>임베딩 갱신일</span>
                                            <span>{new Date(item.embeddingUpdatedAt).toLocaleString()}</span>
                                        </div>
                                    )}
                                </div>
                            </section>
                        </div>

                        <div className="pt-4 h-64 border-t flex flex-col">
                            <h4 className="font-semibold text-xs mb-2">상세 페이지 요약</h4>
                            <iframe
                                className="w-full flex-1 rounded border bg-white"
                                srcDoc={item.detailHtml || '<body style="color: #666; font-size: 12px; text-align: center; padding: 20px;">상세 정보 HTML이 없습니다.</body>'}
                                title="detail-viewer"
                            />
                        </div>

                        <div className="pt-4 sticky bottom-0 bg-background pb-4 space-y-2">
                            <Button
                                className="w-full bg-primary hover:bg-primary/90 text-white font-bold h-12"
                                onClick={handleStartSourcing}
                                disabled={isStartingSourcing}
                            >
                                {isStartingSourcing ? (
                                    <Loader2 className="h-5 w-5 animate-spin mr-2" />
                                ) : (
                                    <Star className="h-5 w-5 mr-2 fill-current" />
                                )}
                                스마트 소싱 시작
                            </Button>
                            <Button
                                variant="outline"
                                className="w-full h-10 text-xs"
                                onClick={() => window.open(item.productUrl, '_blank')}
                            >
                                <ExternalLink className="h-3 w-3 mr-2" />
                                마켓 원문 보기
                            </Button>
                        </div>
                    </div>
                ) : (
                    <div className="p-10 text-center text-muted-foreground">항목을 불러올 수 없습니다.</div>
                )}
            </div>
        </div>
    );
}
