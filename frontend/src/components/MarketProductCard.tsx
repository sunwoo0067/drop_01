import { memo } from "react";
import Image from "next/image";
import {
    ShoppingBag,
    ExternalLink,
    Zap,
    Sparkles
} from "lucide-react";
import { Card, CardContent, CardFooter } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

interface MarketProductCardProps {
    item: {
        id: string;
        productId: string;
        marketItemId: string;
        status: string;
        linkedAt: string | null;
        name: string | null;
        processedName: string | null;
        sellingPrice: number;
        processedImageUrls: string[] | null;
        productStatus: string | null;
        processingStatus: string | null;
        marketAccountId: string;
        accountName: string | null;
        marketCode: string;
    };
    onViewOnCoupang: (marketItemId: string) => void;
    onPremiumOptimize: (productId: string) => void;
}

const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "-";
    const date = new Date(dateStr);
    return date.toLocaleDateString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
};

const MarketProductCard = memo(({ item, onViewOnCoupang, onPremiumOptimize }: MarketProductCardProps) => {
    return (
        <Card
            className="group overflow-hidden border-none shadow-md hover:shadow-2xl transition-all duration-500 rounded-3xl bg-card/40 backdrop-blur-xl border border-white/10"
        >
            {/* 이미지 미리보기 */}
            <div className="aspect-[4/3] relative overflow-hidden bg-muted">
                {item.processedImageUrls && item.processedImageUrls.length > 0 ? (
                    <Image
                        src={item.processedImageUrls[0]}
                        alt={item.name || "상품"}
                        width={400}
                        height={300}
                        className="object-cover w-full h-full transition-transform duration-700 group-hover:scale-110"
                        loading="lazy"
                        sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
                    />
                ) : (
                    <div className="w-full h-full flex flex-col items-center justify-center text-muted-foreground/30 space-y-2">
                        <ShoppingBag className="h-12 w-12" />
                        <span className="text-xs font-medium uppercase tracking-widest">No Image</span>
                    </div>
                )}

                {/* 상태 배지 */}
                <div className="absolute top-4 left-4">
                    <Badge
                        className={cn(
                            "backdrop-blur-md border-0 text-[10px] font-bold tracking-widest uppercase py-1",
                            item.status === "ACTIVE" ? "bg-emerald-500/80 text-white" : "bg-gray-500/80 text-white"
                        )}
                    >
                        {item.status === "ACTIVE" ? "판매중" : item.status}
                    </Badge>
                </div>

                {/* 마켓 계정 배지 */}
                <div className="absolute top-4 right-4">
                    <Badge
                        className={cn(
                            "backdrop-blur-md border-0 text-[10px] font-bold py-1",
                            item.marketCode === "COUPANG" ? "bg-orange-500/80 text-white" : "bg-green-600/80 text-white"
                        )}
                    >
                        {item.accountName || (item.marketCode === "COUPANG" ? "쿠팡" : "스토어")}
                    </Badge>
                </div>

                {/* 외부 링크 */}
                <div className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                        size="icon"
                        variant="secondary"
                        className="h-9 w-9 rounded-full shadow-lg"
                        onClick={() => onViewOnCoupang(item.marketItemId)}
                    >
                        <ExternalLink className="h-4 w-4" />
                    </Button>
                </div>
            </div>

            <CardContent className="p-5 space-y-4">
                <div className="space-y-1">
                    <h3 className="font-bold text-lg leading-tight truncate group-hover:text-primary transition-colors">
                        {item.processedName || item.name || "상품명 없음"}
                    </h3>
                    <p className="text-xs text-muted-foreground truncate">
                        마켓 ID: {item.marketItemId}
                    </p>
                </div>

                <div className="flex items-center justify-between text-sm py-3 border-y border-foreground/5">
                    <div className="flex flex-col">
                        <span className="text-muted-foreground text-[10px] uppercase font-bold tracking-tighter">판매가</span>
                        <span className="font-bold text-base text-primary">{item.sellingPrice.toLocaleString()}원</span>
                    </div>
                    <div className="flex flex-col items-end">
                        <span className="text-muted-foreground text-[10px] uppercase font-bold tracking-tighter">등록일</span>
                        <span className="text-sm">{formatDate(item.linkedAt)}</span>
                    </div>
                </div>
            </CardContent>

            <CardFooter className="px-5 pb-5 pt-0 gap-2">
                <Button
                    className="flex-1 rounded-2xl font-bold bg-accent hover:bg-accent/80 text-foreground border-none transition-all"
                    variant="outline"
                    size="sm"
                    onClick={() => onViewOnCoupang(item.marketItemId)}
                >
                    <ExternalLink className="mr-2 h-4 w-4" />
                    조회
                </Button>
                <Button
                    className={cn(
                        "flex-[1.5] rounded-2xl font-black transition-all",
                        item.processingStatus === "PROCESSING"
                            ? "bg-amber-100 text-amber-600 cursor-not-allowed"
                            : "bg-emerald-500 text-white hover:bg-emerald-600 hover:shadow-lg hover:shadow-emerald-500/30"
                    )}
                    size="sm"
                    disabled={item.processingStatus === "PROCESSING"}
                    onClick={() => onPremiumOptimize(item.productId)}
                >
                    {item.processingStatus === "PROCESSING" ? (
                        <>
                            <Zap className="mr-2 h-4 w-4 animate-pulse" />
                            진행중
                        </>
                    ) : (
                        <>
                            <Sparkles className="mr-2 h-4 w-4" />
                            프리미엄 고도화
                        </>
                    )}
                </Button>
            </CardFooter>
        </Card>
    );
});

MarketProductCard.displayName = "MarketProductCard";

export default MarketProductCard;


