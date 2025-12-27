/**
 * 매출 분석 및 소싱 추천 관련 타입 정의
 */

// ============================================================================
// 매출 분석 타입
// ============================================================================

export interface SalesAnalytics {
    id: string;
    product_id: string;
    period_type: string;
    period_start: string;
    period_end: string;
    total_orders: number;
    total_quantity: number;
    total_revenue: number;
    total_profit: number;
    avg_margin_rate: number;
    order_growth_rate: number;
    revenue_growth_rate: number;
    predicted_orders?: number;
    predicted_revenue?: number;
    prediction_confidence?: number;
    category_trend_score: number;
    market_demand_score: number;
    trend_analysis?: string;
    insights?: string[];
    recommendations?: string[];
    created_at: string;
}

export interface ProductPerformance {
    product_id: string;
    product_name: string;
    total_orders: number;
    total_revenue: number;
    total_profit: number;
    avg_margin_rate: number;
    order_growth_rate: number;
    revenue_growth_rate: number;
    predicted_orders?: number;
    predicted_revenue?: number;
}

export interface SalesSummary {
    total_revenue: number;
    total_orders: number;
    total_profit: number;
    avg_margin_rate: number;
    avg_growth_rate: number;
    period_type: string;
    period_start: string;
    period_end: string;
}

export interface SalesTrendDataPoint {
    period: string;
    period_start: string;
    period_end: string;
    total_orders: number;
    total_revenue: number;
    total_profit: number;
    predicted_orders?: number;
    predicted_revenue?: number;
}

export interface SalesTrend {
    period_type: string;
    data_points: SalesTrendDataPoint[];
}

// ============================================================================
// 소싱 추천 타입
// ============================================================================

export interface SourcingRecommendation {
    id: string;
    product_id?: string;
    product_name?: string;
    recommendation_type: string;
    recommendation_date: string;
    overall_score: number;
    sales_potential_score: number;
    market_trend_score: number;
    profit_margin_score: number;
    supplier_reliability_score: number;
    seasonal_score: number;
    recommended_quantity: number;
    min_quantity: number;
    max_quantity: number;
    current_supply_price: number;
    recommended_selling_price: number;
    expected_margin: number;
    current_stock: number;
    stock_days_left?: number;
    reorder_point: number;
    reasoning?: string;
    risk_factors?: string[];
    opportunity_factors?: string[];
    status: string;
    confidence_level: number;
    created_at: string;
}

export interface RecommendationSummary {
    period_days: number;
    total_recommendations: number;
    pending: number;
    accepted: number;
    rejected: number;
    acceptance_rate: number;
    avg_overall_score: number;
}

export interface ReorderAlert {
    recommendation_id: string;
    product_name: string;
    stock_days_left: number;
    recommended_quantity: number;
    overall_score: number;
}

// ============================================================================
// API 요청 타입
// ============================================================================

export interface AnalyzeProductSalesRequest {
    product_id: string;
    period_type?: string;
    period_count?: number;
}

export interface GenerateRecommendationRequest {
    product_id: string;
    recommendation_type?: string;
}

export interface RecommendationActionRequest {
    action_taken: string;
}

// ============================================================================
// API 응답 타입
// ============================================================================

export interface BulkAnalyticsResponse {
    status: string;
    message: string;
    product_count?: number;
}

export interface BulkRecommendationsResponse {
    status: string;
    message: string;
    limit?: number;
    recommendation_type?: string;
}

export interface ProductAnalyticsHistoryResponse {
    product_id: string;
    product_name: string;
    period_type: string;
    history: SalesAnalytics[];
}

export interface ProductRecommendationsResponse {
    product_id: string;
    product_name: string;
    recommendations: SourcingRecommendation[];
}

export interface ReorderAlertsResponse {
    alert_count: number;
    alerts: ReorderAlert[];
}
