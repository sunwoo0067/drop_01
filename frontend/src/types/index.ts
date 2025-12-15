export interface Product {
    id: string;
    name: string;
    processed_name?: string;
    brand?: string;
    selling_price: number;
    processing_status: string;
    processed_image_urls?: string[];
    created_at: string;
}

export interface MarketListing {
    id: string;
    product_id: string;
    market_item_id: string;
    status: string;
}
