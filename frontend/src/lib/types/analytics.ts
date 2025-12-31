/**
 * 매출 분석 및 소싱 추천 관련 타입 정의
 */

// ============================================================================
// 매출 분석 타입
// ============================================================================

export interface OptionPerformance {
    option_id: string;
    option_name: string;
    option_value: string;
    total_quantity: number;
    total_revenue: number;
    total_cost: number;
    total_profit: number;
    avg_margin_rate: number;
}

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
    option_performance?: OptionPerformance[];
    // 추가된 정밀 재무 지표
    actual_fees?: number;
    actual_vat?: number;
    net_settlement?: number;
}

export interface StrategicReport {
    market_position: string;
    swot_analysis: {
        strengths: string[];
        weaknesses: string[];
        opportunities: string[];
        threats: string[];
    };
    pricing_strategy: string;
    action_plan: string[];
    expected_impact: string;
}

export interface OptimalPricePrediction {
    optimal_price: number;
    strategy: string;
    reason: string;
    expected_margin_rate: number;
    impact: string;
    market_code?: string | null;
    account_id?: string | null;
    market_item_id?: string | null;
}

export interface UpdatePriceRequest {
    market_code: string;
    account_id: string;
    market_item_id: string;
    price: number;
}

export interface UpdatePriceResponse {
    success: boolean;
    message?: string;
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
    // 추가된 정밀 재무 지표
    actual_fees?: number;
    actual_vat?: number;
    net_settlement?: number;
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

export interface MarginTrendItem {
    date: string;
    avg_margin: number;
    total_profit: number;
    order_count: number;
}

export interface PricingSimulation {
    pending_reco_count: number;
    current_base_profit: number;
    simulated_profit: number;
    expected_lift: number;
    lift_percentage: number;
}

export interface PricingRecommendation {
    id: string;
    product_id: string;
    product_name?: string;
    market_account_id: string;
    current_price: number;
    recommended_price: number;
    expected_margin?: number;
    confidence: number;
    reasons?: string[];
    status: string;
    created_at: string;
}

export interface PricingSettings {
    market_account_id: string;
    auto_mode: string;
    confidence_threshold: number;
    max_changes_per_hour: number;
    cooldown_hours: number;
}

export interface ThrottleStatus {
    usage: number;
    limit: number;
    name: string;
}

export interface AutomationStats {
    total_recommendations: number;
    pending_count: number;
    applied_24h: number;
    throttle_status: Record<string, ThrottleStatus>;
}

// ============================================================================
// 소싱 추천 타입
// ============================================================================

export interface OptionRecommendation {
    option_id?: string;
    option_name: string;
    option_value: string;
    total_quantity: number;
    total_revenue: number;
    total_profit: number;
    avg_margin_rate: number;
    recommended_quantity: number;
    score: number;
}

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
    option_recommendations?: OptionRecommendation[];
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

export interface ScalingRecommendation {
    product_id: string;
    product_name: string;
    current_orders: number;
    source_market: string;
    target_market: string;
    expected_impact: 'High' | 'Medium' | 'Low';
    difficulty_score: 'High' | 'Medium' | 'Low';
    potential_revenue: number;
    reason: string;
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
