"use client";

import React, { useState, useEffect } from 'react';

interface Product {
  id: string;
  name: string;
  lifecycle_stage: string;
  lifecycle_stage_updated_at: string | null;
  total_sales_count: number;
  total_views: number;
  total_clicks: number;
  ctr: number;
  conversion_rate: number;
  total_revenue: number;
  processing_status: string;
  status: string;
}

interface StageDistribution {
  STEP_1: number;
  STEP_2: number;
  STEP_3: number;
}

export default function LifecycleDashboard() {
  const [stageDistribution, setStageDistribution] = useState<StageDistribution>({
    STEP_1: 0,
    STEP_2: 0,
    STEP_3: 0,
  });
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedStage, setSelectedStage] = useState<string>("ALL");
  const [loading, setLoading] = useState(true);
  const [autoTransitions, setAutoTransitions] = useState<any>(null);

  // 라이프사이클 단계별 상품 조회
  const fetchProductsByStage = async (stage: string) => {
    try {
      const response = await fetch(`/api/products/by-stage/${stage}?limit=50`);
      const data = await response.json();
      setProducts(data.products || []);
    } catch (error) {
      console.error("Failed to fetch products:", error);
    }
  };

  // 단계별 분포 조회
  const fetchStageDistribution = async () => {
    try {
      const response = await fetch("/api/lifecycle/distribution");
      const data = await response.json();
      setStageDistribution(data.distribution);
    } catch (error) {
      console.error("Failed to fetch stage distribution:", error);
    }
  };

  // 자동 전환 실행
  const runAutoTransition = async () => {
    if (!confirm("자동 단계 전환을 실행하시겠습니까? (dry_run=False)")) {
      return;
    }

    try {
      const response = await fetch("/api/lifecycle/check-all-transitions?dry_run=false", {
        method: "POST",
      });
      const data = await response.json();
      setAutoTransitions(data);
      alert(`전환 완료:\nSTEP 1→2: ${data.step1_to_step2?.transitioned || 0}건\nSTEP 2→3: ${data.step2_to_step3?.transitioned || 0}건`);
      // 데이터 새로고침
      fetchStageDistribution();
      if (selectedStage !== "ALL") {
        fetchProductsByStage(selectedStage);
      }
    } catch (error) {
      console.error("Failed to run auto transition:", error);
      alert("전환 실패: " + error);
    }
  };

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await fetchStageDistribution();
      if (selectedStage !== "ALL") {
        await fetchProductsByStage(selectedStage);
      }
      setLoading(false);
    };

    loadData();
  }, [selectedStage]);

  const getStageColor = (stage: string) => {
    switch (stage) {
      case "STEP_1":
        return "bg-blue-100 text-blue-800";
      case "STEP_2":
        return "bg-green-100 text-green-800";
      case "STEP_3":
        return "bg-purple-100 text-purple-800";
      default:
        return "bg-gray-100 text-gray-800";
    }
  };

  const getStageName = (stage: string) => {
    switch (stage) {
      case "STEP_1":
        return "탐색";
      case "STEP_2":
        return "검증";
      case "STEP_3":
        return "스케일";
      default:
        return stage;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* 헤더 */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            라이프사이클 대시보드
          </h1>
          <p className="text-gray-600">
            3단계 드롭쉬핑 전략 (탐색 → 검증 → 스케일) 모니터링
          </p>
        </div>

        {/* 단계별 분포 카드 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {Object.entries(stageDistribution).map(([stage, count]) => (
            <div
              key={stage}
              className={`p-6 rounded-lg border-2 cursor-pointer transition-all ${
                selectedStage === stage
                  ? "border-indigo-600 shadow-lg"
                  : "border-gray-200 hover:border-gray-300"
              }`}
              onClick={() => setSelectedStage(stage)}
            >
              <div className="text-sm font-medium text-gray-500 mb-2">
                {getStageName(stage)}
              </div>
              <div className="text-3xl font-bold text-gray-900 mb-1">
                {count}
              </div>
              <div className="text-sm text-gray-600">
                상품
              </div>
            </div>
          ))}
          
          {/* 전체 버튼 */}
          <div
            className={`p-6 rounded-lg border-2 cursor-pointer transition-all ${
              selectedStage === "ALL"
                ? "border-indigo-600 shadow-lg"
                : "border-gray-200 hover:border-gray-300"
            }`}
            onClick={() => setSelectedStage("ALL")}
          >
            <div className="text-sm font-medium text-gray-500 mb-2">
              전체
            </div>
            <div className="text-3xl font-bold text-gray-900 mb-1">
              {Object.values(stageDistribution).reduce((a, b) => a + b, 0)}
            </div>
            <div className="text-sm text-gray-600">
              상품
            </div>
          </div>
        </div>

        {/* 자동 전환 버튼 */}
        <div className="mb-8 flex justify-end">
          <button
            onClick={runAutoTransition}
            className="px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors font-medium"
          >
            자동 단계 전환 실행
          </button>
        </div>

        {/* 상품 목록 */}
        {selectedStage !== "ALL" && (
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-xl font-semibold text-gray-900">
                {getStageName(selectedStage)} 상품 목록
              </h2>
            </div>
            
            {loading ? (
              <div className="p-8 text-center text-gray-500">
                로딩 중...
              </div>
            ) : products.length === 0 ? (
              <div className="p-8 text-center text-gray-500">
                상품이 없습니다.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        상품명
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        단계
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        판매
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        노출
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        CTR
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        전환율
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        매출
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        상태
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {products.map((product) => (
                      <tr key={product.id} className="hover:bg-gray-50">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm font-medium text-gray-900">
                            {product.name}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getStageColor(product.lifecycle_stage)}`}>
                            {getStageName(product.lifecycle_stage)}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-gray-900">
                          {product.total_sales_count}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-gray-900">
                          {product.total_views.toLocaleString()}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-gray-900">
                          {(product.ctr * 100).toFixed(2)}%
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-gray-900">
                          {(product.conversion_rate * 100).toFixed(2)}%
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-gray-900">
                          ₩{product.total_revenue.toLocaleString()}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                            product.status === "ACTIVE"
                              ? "bg-green-100 text-green-800"
                              : "bg-gray-100 text-gray-800"
                          }`}>
                            {product.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* 단계별 설명 */}
        <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-blue-50 p-6 rounded-lg">
            <h3 className="text-lg font-semibold text-blue-900 mb-2">
              STEP 1: 탐색
            </h3>
            <ul className="text-sm text-blue-800 space-y-1">
              <li>• 대량 상품 등록</li>
              <li>• 상품명만 최소 가공</li>
              <li>• CTR ≥ 2% → STEP 2</li>
              <li>• 최소 AI 비용</li>
            </ul>
          </div>
          
          <div className="bg-green-50 p-6 rounded-lg">
            <h3 className="text-lg font-semibold text-green-900 mb-2">
              STEP 2: 검증
            </h3>
            <ul className="text-sm text-green-800 space-y-1">
              <li>• 최소 1회 판매 상품</li>
              <li>• 텍스트 중심 가공</li>
              <li>• 판매 ≥ 5 → STEP 3</li>
              <li>• 중간 AI 비용</li>
            </ul>
          </div>
          
          <div className="bg-purple-50 p-6 rounded-lg">
            <h3 className="text-lg font-semibold text-purple-900 mb-2">
              STEP 3: 스케일
            </h3>
            <ul className="text-sm text-purple-800 space-y-1">
              <li>• 검증된 상품 완전 브랜딩</li>
              <li>• 이미지·상세페이지 완전 교체</li>
              <li>• 고품질 AI 사용</li>
              <li>• 최대 ROI</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

