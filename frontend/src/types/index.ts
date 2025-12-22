export interface Product {
    id: string;
    name: string;
    processed_name?: string;
    brand?: string;
    selling_price: number;
    processing_status: string;
    processed_image_urls?: string[];
    processed_keywords?: string[];
    created_at: string;
    status: string;
    market_listings?: MarketListing[];
}

export interface MarketProduct {
    id: string;
    productId?: string | null;
    marketAccountId: string;
    marketItemId: string;
    status: string;
    coupangStatus?: string | null;
    rejectionReason?: {
        statusName?: string;
        reason?: string;
        approvalDate?: string;
        [key: string]: any;
    } | null;
    linkedAt?: string | null;
    name?: string | null;
    processedName?: string | null;
    sellingPrice?: number;
    processedImageUrls?: string[] | null;
    productStatus?: string | null;
}

export interface SourcingCandidate {
    id: string;
    supplierCode: string;
    supplierItemId: string;
    name: string;
    supplyPrice: number;
    sourceStrategy: string;
    benchmarkProductId?: string | null;
    similarityScore?: number | null;
    seasonalScore?: number | null;
    marginScore?: number | null;
    finalScore?: number | null;
    specData?: Record<string, any> | null;
    seoKeywords?: string[] | null;
    targetEvent?: string | null;
    thumbnailUrl?: string | null;
    status: string;
    createdAt?: string | null;
}

export interface MarketListing {
    id: string;
    market_account_id: string;
    market_item_id: string;
    status: string;
    coupang_status?: string | null;
    rejection_reason?: {
        statusName?: string;
        reason?: string;
        approvalDate?: string;
        [key: string]: any;
    } | null;
}
