export interface BenchmarkProduct {
    id: string;
    marketCode: string;
    productId: string;
    name: string;
    price: number;
    productUrl: string;
    imageUrls?: string[];
    detailHtmlLen: number;
    rawHtmlLen: number;
    blockedReason?: string;
    reviewSummary?: string;
    painPoints?: string[];
    createdAt: string;
    updatedAt: string;
}
