/**
 * 매출 분석 및 소싱 추천 API 클라이언트
 */
import api from './api';
import type {
    SalesAnalytics,
    OptionPerformance,
    ProductPerformance,
    SalesSummary,
    SalesTrend,
    SourcingRecommendation,
    RecommendationSummary,
    AnalyzeProductSalesRequest,
    GenerateRecommendationRequest,
    RecommendationActionRequest,
    BulkRecommendationsResponse,
    ProductAnalyticsHistoryResponse,
    ProductRecommendationsResponse,
    ReorderAlertsResponse,
    StrategicReport,
    OptimalPricePrediction,
    UpdatePriceRequest,
    UpdatePriceResponse,
    ScalingRecommendation,
    ScalingRecommendation,
    BulkAnalyticsResponse,
    MarginTrendItem,
    PricingSimulation,
    PricingRecommendation,
    PricingSettings,
    AutomationStats,
} from './types/analytics';

// ============================================================================
// 매출 분석 API
// ============================================================================

export const analyticsAPI = {
    /**
     * 매출 요약 조회
     */
    getSummary: async (periodType: string = 'weekly'): Promise<SalesSummary> => {
        const response = await api.get('/analytics/summary', {
            params: { period_type: periodType },
        });
        return response.data;
    },

    /**
     * 매출 추이 조회
     */
    getTrend: async (periodType: string = 'weekly', periods: number = 12): Promise<SalesTrend> => {
        const response = await api.get('/analytics/trend', {
            params: { period_type: periodType, periods },
        });
        return response.data;
    },

    /**
     * 상위 성과 제품 목록 조회
     */
    getTopPerforming: async (limit: number = 10, periodType: string = 'weekly'): Promise<ProductPerformance[]> => {
        const response = await api.get('/analytics/top-performing', {
            params: { limit, period_type: periodType },
        });
        return response.data;
    },

    /**
     * 저성과 제품 목록 조회
     */
    getLowPerforming: async (limit: number = 10, periodType: string = 'weekly'): Promise<ProductPerformance[]> => {
        const response = await api.get('/analytics/low-performing', {
            params: { limit, period_type: periodType },
        });
        return response.data;
    },

    /**
     * 제품별 매출 분석 조회
     */
    getProductAnalytics: async (productId: string, periodType: string = 'weekly'): Promise<SalesAnalytics> => {
        const response = await api.get(`/analytics/product/${productId}`, {
            params: { period_type: periodType },
        });
        return response.data;
    },

    /**
     * 제품별 매출 분석 이력 조회
     */
    getProductAnalyticsHistory: async (
        productId: string,
        periodType: string = 'weekly',
        limit: number = 12
    ): Promise<ProductAnalyticsHistoryResponse> => {
        const response = await api.get(`/analytics/product/${productId}/history`, {
            params: { period_type: periodType, limit },
        });
        return response.data;
    },

    /**
     * 제품별 옵션 상세 성과 조회
     */
    getProductOptionPerformance: async (
        productId: string,
        periodType: string = 'weekly',
        periodCount: number = 4
    ): Promise<OptionPerformance[]> => {
        const response = await api.get(`/analytics/product/${productId}/options`, {
            params: { period_type: periodType, period_count: periodCount },
        });
        return response.data;
    },

    /**
     * 제품별 매출 분석 생성
     */
    analyzeProductSales: async (request: AnalyzeProductSalesRequest): Promise<SalesAnalytics> => {
        const response = await api.post('/analytics/analyze-product', request);
        return response.data;
    },

    /**
     * 제품 ID로 매출 분석 생성
     */
    analyzeProductById: async (
        productId: string,
        periodType: string = 'weekly',
        periodCount: number = 4
    ): Promise<SalesAnalytics> => {
        const response = await api.post(`/analytics/analyze-product/${productId}`, null, {
            params: { period_type: periodType, period_count: periodCount },
        });
        return response.data;
    },

    /**
     * 대량 매출 분석 실행
     */
    triggerBulkAnalyze: async (limit: number = 50, periodType: string = 'weekly'): Promise<BulkAnalyticsResponse> => {
        const response = await api.post('/analytics/bulk-analyze', null, {
            params: { limit, period_type: periodType },
        });
        return response.data;
    },

    /**
     * AI 전략 보고서 조회
     */
    getStrategicReport: async (productId: string): Promise<StrategicReport> => {
        const response = await api.get(`/analytics/strategic-report/${productId}`);
        return response.data;
    },

    /**
     * AI 최적 가격 제안 조회
     */
    getOptimalPricePrediction: async (productId: string): Promise<OptimalPricePrediction> => {
        const response = await api.get(`/analytics/optimal-price/${productId}`);
        return response.data;
    },

    /**
     * 마켓 상품 판매가 수정
     */
    updatePrice: async (request: UpdatePriceRequest): Promise<UpdatePriceResponse> => {
        const response = await api.post('/analytics/update-price', request);
        return response.data;
    },

    /**
     * 일자별 마진율 트렌드 조회 (Admin)
     */
    getMarginTrend: async (days: number = 30): Promise<MarginTrendItem[]> => {
        const response = await api.get('/admin/analytics/margin-trend', {
            params: { days },
        });
        return response.data;
    },

    /**
     * 가격 권고 적용 시뮬레이션 조회 (Admin)
     */
    getPricingSimulation: async (): Promise<PricingSimulation> => {
        const response = await api.get('/admin/analytics/simulation');
        return response.data;
    },
};

// ============================================================================
// 가격 관리 API (Admin)
// ============================================================================

export const pricingAPI = {
    /**
     * 가격 권고 리스트 조회
     */
    getRecommendations: async (status: string = 'PENDING', limit: number = 50): Promise<PricingRecommendation[]> => {
        const response = await api.get('/admin/pricing/recommendations', {
            params: { status, limit },
        });
        return response.data;
    },

    /**
     * 가격 권고 수동 승인 및 적용
     */
    applyRecommendation: async (recoId: string): Promise<{ success: boolean; message: string }> => {
        const response = await api.post(`/admin/pricing/recommendations/${recoId}/apply`);
        return response.data;
    },

    /**
     * 계정별 가격 자동화 설정 조회
     */
    getSettings: async (accountId: string): Promise<PricingSettings> => {
        const response = await api.get(`/admin/pricing/settings/${accountId}`);
        return response.data;
    },

    /**
     * 계정별 가격 자동화 설정 수정
     */
    updateSettings: async (accountId: string, updates: Partial<PricingSettings>): Promise<PricingSettings> => {
        const response = await api.patch(`/admin/pricing/settings/${accountId}`, updates);
        return response.data;
    },

    /**
     * 가격 자동화 시스템 가동 현황 및 통계 조회
     */
    getStats: async (): Promise<AutomationStats> => {
        const response = await api.get('/admin/pricing/stats');
        return response.data;
    },
};

// ============================================================================
// 소싱 추천 API
// ============================================================================

export const recommendationsAPI = {
    /**
     * 소싱 추천 생성
     */
    generate: async (request: GenerateRecommendationRequest): Promise<SourcingRecommendation> => {
        const response = await api.post('/recommendations/generate', request);
        return response.data;
    },

    /**
     * 제품 ID로 소싱 추천 생성
     */
    generateById: async (
        productId: string,
        recommendationType: string = 'REORDER'
    ): Promise<SourcingRecommendation> => {
        const response = await api.post(`/recommendations/generate/${productId}`, null, {
            params: { recommendation_type: recommendationType },
        });
        return response.data;
    },

    /**
     * 대기 중인 소싱 추천 목록 조회
     */
    getPending: async (limit: number = 20): Promise<SourcingRecommendation[]> => {
        const response = await api.get('/recommendations/pending', {
            params: { limit },
        });
        return response.data;
    },

    /**
     * 특정 소싱 추천 조회
     */
    getRecommendation: async (recommendationId: string): Promise<SourcingRecommendation> => {
        const response = await api.get(`/recommendations/${recommendationId}`);
        return response.data;
    },

    /**
     * 제품별 소싱 추천 목록 조회
     */
    getProductRecommendations: async (
        productId: string,
        status?: string,
        limit: number = 10
    ): Promise<ProductRecommendationsResponse> => {
        const response = await api.get(`/recommendations/product/${productId}`, {
            params: { status, limit },
        });
        return response.data;
    },

    /**
     * 소싱 추천 수락
     */
    acceptRecommendation: async (
        recommendationId: string,
        action: RecommendationActionRequest
    ): Promise<SourcingRecommendation> => {
        const response = await api.patch(`/recommendations/${recommendationId}/accept`, action);
        return response.data;
    },

    /**
     * 소싱 추천 거부
     */
    rejectRecommendation: async (
        recommendationId: string,
        action: RecommendationActionRequest
    ): Promise<SourcingRecommendation> => {
        const response = await api.patch(`/recommendations/${recommendationId}/reject`, action);
        return response.data;
    },

    /**
     * 소싱 추천 요약 조회
     */
    getSummary: async (days: number = 7): Promise<RecommendationSummary> => {
        const response = await api.get('/recommendations/summary', {
            params: { days },
        });
        return response.data;
    },

    /**
     * 높은 우선순위 소싱 추천 조회
     */
    getHighPriority: async (limit: number = 10, minScore: number = 70.0): Promise<SourcingRecommendation[]> => {
        const response = await api.get('/recommendations/high-priority', {
            params: { limit, min_score: minScore },
        });
        return response.data;
    },

    /**
     * 재주문 알림 조회
     */
    getReorderAlerts: async (): Promise<ReorderAlertsResponse> => {
        const response = await api.get('/recommendations/reorder-alerts');
        return response.data;
    },

    /**
     * 대량 소싱 추천 생성
     */
    triggerBulkGenerate: async (
        limit: number = 50,
        recommendationType: string = 'REORDER'
    ): Promise<BulkRecommendationsResponse> => {
        const response = await api.post('/recommendations/bulk-generate', null, {
            params: { limit, recommendation_type: recommendationType },
        });
        return response.data;
    },

    /**
     * 다채널 확장 추천 목록 조회
     */
    getScalingRecommendations: async (limit: number = 10): Promise<ScalingRecommendation[]> => {
        const response = await api.get('/recommendations/scaling', {
            params: { limit },
        });
        return response.data;
    },
};

// ============================================================================
// 통합 API
// ============================================================================

export const analyticsClient = {
    ...analyticsAPI,
    ...recommendationsAPI,
    ...pricingAPI,
};
