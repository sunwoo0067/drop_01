"""
KPI (Key Performance Indicator) API 엔드포인트

마켓별로 들어오는 KPI 데이터를 수집하여 상품별 성과를 추적합니다.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Product, MarketListing, OrderItem, Order
from app.services.product_lifecycle_service import ProductLifecycleService
from app.services.processing_history_service import ProcessingHistoryService

router = APIRouter()
logger = logging.getLogger(__name__)


# ==================== Request/Response Models ====================

class MarketListingKPIUpdate(BaseModel):
    """마켓 리스팅 KPI 업데이트 요청"""
    listing_id: uuid.UUID = Field(..., description="마켓 리스팅 ID")
    view_count: int = Field(default=0, ge=0, description="노출수")
    click_count: int = Field(default=0, ge=0, description="클릭수")
    kpi_updated_at: datetime = Field(default_factory=datetime.now, description="KPI 업데이트 시점")


class OrderKPIUpdate(BaseModel):
    """주문 KPI 업데이트 요청"""
    order_id: uuid.UUID = Field(..., description="주문 ID")
    product_id: uuid.UUID = Field(..., description="상품 ID")
    quantity: int = Field(default=1, ge=1, description="주문 수량")
    unit_price: int = Field(default=0, ge=0, description="단가")
    customer_id: Optional[str] = Field(default=None, description="고객 ID")
    order_date: datetime = Field(default_factory=datetime.now, description="주문 일시")


class BulkKPIUpdate(BaseModel):
    """대량 KPI 업데이트 요청"""
    listings: List[MarketListingKPIUpdate] = Field(default=[], description="마켓 리스팅 KPI 리스트")
    orders: List[OrderKPIUpdate] = Field(default=[], description="주문 KPI 리스트")


# ==================== 마켓 리스팅 KPI 업데이트 ====================

@router.post("/market-listings/kpi/bulk-update")
async def bulk_update_market_listing_kpi(
    request: BulkKPIUpdate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    대량 마켓 리스팅 KPI 업데이트
    
    여러 마켓 리스팅의 노출/클릭 데이터를 일괄 업데이트합니다.
    
    Args:
        request: 대량 KPI 업데이트 요청 (listings, orders)
        
    Returns:
        {
            "listings_updated": 10,
            "orders_processed": 5,
            "details": {...}
        }
    """
    try:
        results = {
            "listings_updated": 0,
            "listings_failed": 0,
            "orders_processed": 0,
            "orders_failed": 0,
            "errors": []
        }
        
        # 1. 마켓 리스팅 KPI 업데이트
        for listing_kpi in request.listings:
            try:
                listing = session.get(MarketListing, listing_kpi.listing_id)
                if not listing:
                    results["listings_failed"] += 1
                    continue
                
                # KPI 업데이트
                listing.view_count = listing_kpi.view_count
                listing.click_count = listing_kpi.click_count
                listing.kpi_updated_at = listing_kpi.kpi_updated_at
                
                results["listings_updated"] += 1
                
            except Exception as e:
                results["listings_failed"] += 1
                results["errors"].append(f"Listing {listing_kpi.listing_id}: {str(e)[:50]}")
                logger.error(f"Failed to update KPI for listing {listing_kpi.listing_id}: {e}")
        
        # 2. 주문 KPI 업데이트 (백그라운드로 수행)
        if request.orders:
            background_tasks.add_task(
                _process_orders_kpi,
                [order.model_dump() for order in request.orders]
            )
            results["orders_processed"] = len(request.orders)
        
        session.commit()
        
        logger.info(f"Bulk KPI update completed: "
                   f"listings_updated={results['listings_updated']}, "
                   f"listings_failed={results['listings_failed']}, "
                   f"orders_queued={results['orders_processed']}")
        
        return results
        
    except Exception as e:
        logger.error(f"Bulk KPI update failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"업데이트 실패: {str(e)}")


@router.post("/market-listings/{listing_id}/kpi")
async def update_market_listing_kpi(
    listing_id: uuid.UUID,
    request: MarketListingKPIUpdate,
    session: Session = Depends(get_session)
):
    """
    마켓 리스팅 KPI 업데이트 (단일)
    
    Args:
        listing_id: 마켓 리스팅 ID
        request: KPI 업데이트 요청
        
    Returns:
        업데이트 결과
    """
    try:
        listing = session.get(MarketListing, listing_id)
        if not listing:
            raise HTTPException(status_code=404, detail=f"마켓 리스팅을 찾을 수 없습니다: {listing_id}")
        
        # KPI 업데이트
        listing.view_count = request.view_count
        listing.click_count = request.click_count
        listing.kpi_updated_at = request.kpi_updated_at
        
        session.commit()
        session.refresh(listing)
        
        logger.info(f"Updated KPI for listing {listing_id}: "
                   f"views={request.view_count}, clicks={request.click_count}")
        
        return {
            "listing_id": str(listing_id),
            "product_id": str(listing.product_id),
            "view_count": listing.view_count,
            "click_count": listing.click_count,
            "ctr": listing.click_count / listing.view_count if listing.view_count > 0 else 0.0,
            "kpi_updated_at": listing.kpi_updated_at.isoformat() if listing.kpi_updated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update KPI for listing {listing_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"업데이트 실패: {str(e)}")


# ==================== 주문 KPI 업데이트 ====================

@router.post("/orders/kpi/bulk-update")
async def bulk_update_orders_kpi(
    request: List[OrderKPIUpdate],
    session: Session = Depends(get_session)
):
    """
    대량 주문 KPI 업데이트
    
    여러 주문 데이터를 일괄 업데이트합니다.
    
    Args:
        request: 주문 KPI 리스트
        
    Returns:
        {
            "orders_processed": 10,
            "orders_failed": 0,
            "details": {...}
        }
    """
    try:
        results = {
            "orders_processed": 0,
            "orders_failed": 0,
            "products_updated": [],
            "errors": []
        }
        
        for order_kpi in request:
            try:
                # 주문 엔티티 확인 (이미 있는지 체크)
                order = session.get(Order, order_kpi.order_id)
                
                if order:
                    # 기존 주문 업데이트
                    order.product_id = order_kpi.product_id
                    order.quantity = order_kpi.quantity
                    order.unit_price = order_kpi.unit_price
                    order.customer_id = order_kpi.customer_id
                    order.created_at = order_kpi.order_date
                else:
                    # 새 주문 생성
                    order = Order(
                        id=order_kpi.order_id,
                        product_id=order_kpi.product_id,
                        quantity=order_kpi.quantity,
                        unit_price=order_kpi.unit_price,
                        customer_id=order_kpi.customer_id,
                        created_at=order_kpi.order_date
                    )
                    session.add(order)
                
                # OrderItem 생성/업데이트
                order_item = session.query(OrderItem).filter_by(
                    order_id=order_kpi.order_id,
                    product_id=order_kpi.product_id
                ).one_or_none()
                
                if order_item:
                    order_item.quantity = order_kpi.quantity
                    order_item.unit_price = order_kpi.unit_price
                else:
                    order_item = OrderItem(
                        order_id=order_kpi.order_id,
                        product_id=order_kpi.product_id,
                        quantity=order_kpi.quantity,
                        unit_price=order_kpi.unit_price
                    )
                    session.add(order_item)
                
                results["orders_processed"] += 1
                
                # 상품별로 중복 제거
                if str(order_kpi.product_id) not in results["products_updated"]:
                    results["products_updated"].append(str(order_kpi.product_id))
                
            except Exception as e:
                results["orders_failed"] += 1
                results["errors"].append(f"Order {order_kpi.order_id}: {str(e)[:50]}")
                logger.error(f"Failed to update order KPI {order_kpi.order_id}: {e}")
        
        session.commit()
        
        logger.info(f"Bulk order KPI update completed: "
                   f"orders_processed={results['orders_processed']}, "
                   f"orders_failed={results['orders_failed']}")
        
        return results
        
    except Exception as e:
        logger.error(f"Bulk order KPI update failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"업데이트 실패: {str(e)}")


# ==================== 상품별 KPI 조회 ====================

@router.get("/products/{product_id}/kpi")
async def get_product_kpi(
    product_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    """
    상품별 KPI 조회
    
    Args:
        product_id: 상품 ID
        
    Returns:
        상품 KPI 요약
    """
    try:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"상품을 찾을 수 없습니다: {product_id}")
        
        # 마켓별 KPI 집계
        market_kpi_stmt = """
            SELECT 
                ml.market_code,
                SUM(ml.view_count) as total_views,
                SUM(ml.click_count) as total_clicks,
                ml.kpi_updated_at
            FROM market_listings ml
            WHERE ml.product_id = %s
            GROUP BY ml.market_code, ml.kpi_updated_at
        """
        market_kpi_results = session.execute(market_kpi_stmt, [str(product_id)]).all()
        
        market_kpi = [
            {
                "market_code": r[0],
                "total_views": r[1] or 0,
                "total_clicks": r[2] or 0,
                "ctr": (r[2] / r[1]) if r[1] and r[1] > 0 else 0.0,
                "kpi_updated_at": r[3].isoformat() if r[3] else None
            }
            for r in market_kpi_results
        ]
        
        # 전체 집계
        total_views = sum(product.total_views for product in [product])  # 단일 상품이므로 바로 사용
        total_clicks = product.total_clicks
        ctr = product.ctr
        
        return {
            "product_id": str(product_id),
            "name": product.name,
            "lifecycle_stage": product.lifecycle_stage,
            "kpi": {
                "total_views": product.total_views,
                "total_clicks": product.total_clicks,
                "ctr": product.ctr,
                "total_sales_count": product.total_sales_count,
                "total_revenue": product.total_revenue,
                "conversion_rate": product.conversion_rate,
                "repeat_purchase_count": product.repeat_purchase_count,
                "customer_retention_rate": product.customer_retention_rate,
                "avg_customer_value": product.avg_customer_value
            },
            "market_breakdown": market_kpi
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get product KPI {product_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")


# ==================== 상품별 KPI 자동 계산 및 업데이트 ====================

@router.post("/products/{product_id}/kpi/calculate")
async def calculate_product_kpi(
    product_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    """
    상품별 KPI 자동 계산 및 업데이트
    
    마켓별 노출/클릭 데이터와 주문 데이터를 집계하여 상품 KPI를 계산합니다.
    
    Args:
        product_id: 상품 ID
        
    Returns:
        계산된 KPI 데이터
    """
    try:
        lifecycle_service = ProductLifecycleService(session)
        kpi_data = lifecycle_service.update_product_kpi(product_id)
        
        logger.info(f"Calculated KPI for product {product_id}: "
                   f"sales={kpi_data['total_sales_count']}, "
                   f"revenue={kpi_data['total_revenue']}")
        
        return {
            "message": "KPI가 계산 및 업데이트되었습니다",
            "product_id": str(product_id),
            "kpi": kpi_data
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to calculate KPI for product {product_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"계산 실패: {str(e)}")


@router.post("/products/kpi/bulk-calculate")
async def bulk_calculate_products_kpi(
    product_ids: List[uuid.UUID],
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    대량 상품 KPI 자동 계산 및 업데이트
    
    여러 상품의 KPI를 일괄 계산합니다. 백그라운드로 실행됩니다.
    
    Args:
        product_ids: 상품 ID 리스트
        
    Returns:
        {
            "queued": 10,
            "message": "백그라운드에서 KPI 계산을 시작합니다"
        }
    """
    async def _bulk_calculate():
        from app.session_factory import session_factory
        
        results = {
            "processed": 0,
            "failed": 0,
            "errors": []
        }
        
        for product_id in product_ids:
            try:
                with session_factory() as db:
                    lifecycle_service = ProductLifecycleService(db)
                    lifecycle_service.update_product_kpi(product_id)
                    results["processed"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"{product_id}: {str(e)[:50]}")
                logger.error(f"Failed to calculate KPI for product {product_id}: {e}")
        
        logger.info(f"Bulk KPI calculation completed: "
                   f"processed={results['processed']}, "
                   f"failed={results['failed']}")
    
    background_tasks.add_task(_bulk_calculate)
    
    return {
        "queued": len(product_ids),
        "message": "백그라운드에서 KPI 계산을 시작합니다"
    }


# ==================== 가공 영향 측정 ====================

@router.post("/processing-histories/{history_id}/measure-impact")
async def measure_processing_impact(
    history_id: uuid.UUID,
    days_after: int = Query(default=7, ge=1, le=30),
    session: Session = Depends(get_session)
):
    """
    가공 영향 측정
    
    가공 후 N일간의 KPI 변화를 측정합니다.
    
    Args:
        history_id: 가공 이력 ID
        days_after: 가공 후 측정 기간 (일)
        
    Returns:
        {
            "history_id": "...",
            "impact": {
                "before_kpi": {...},
                "after_kpi": {...},
                "improvement": {...},
                "roi_score": 85.5
            }
        }
    """
    try:
        history_service = ProcessingHistoryService(session)
        impact = history_service.measure_processing_impact(history_id, days_after)
        
        return {
            "history_id": str(history_id),
            "days_measured": days_after,
            "impact": impact
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to measure processing impact {history_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"측정 실패: {str(e)}")


# ==================== 내부 헬퍼 함수 ====================

async def _process_orders_kpi(order_data_list: List[dict]):
    """
    주문 KPI 처리 (백그라운드)
    
    Args:
        order_data_list: 주문 데이터 리스트
    """
    from app.session_factory import session_factory
    
    processed = 0
    failed = 0
    
    try:
        with session_factory() as session:
            for order_data in order_data_list:
                try:
                    order_kpi = OrderKPIUpdate(**order_data)
                    
                    # 주문 확인
                    order = session.get(Order, order_kpi.order_id)
                    
                    if order:
                        order.product_id = order_kpi.product_id
                        order.quantity = order_kpi.quantity
                        order.unit_price = order_kpi.unit_price
                        order.customer_id = order_kpi.customer_id
                        order.created_at = order_kpi.order_date
                    else:
                        order = Order(
                            id=order_kpi.order_id,
                            product_id=order_kpi.product_id,
                            quantity=order_kpi.quantity,
                            unit_price=order_kpi.unit_price,
                            customer_id=order_kpi.customer_id,
                            created_at=order_kpi.order_date
                        )
                        session.add(order)
                    
                    # OrderItem 확인
                    order_item = session.query(OrderItem).filter_by(
                        order_id=order_kpi.order_id,
                        product_id=order_kpi.product_id
                    ).one_or_none()
                    
                    if order_item:
                        order_item.quantity = order_kpi.quantity
                        order_item.unit_price = order_kpi.unit_price
                    else:
                        order_item = OrderItem(
                            order_id=order_kpi.order_id,
                            product_id=order_kpi.product_id,
                            quantity=order_kpi.quantity,
                            unit_price=order_kpi.unit_price
                        )
                        session.add(order_item)
                    
                    processed += 1
                    
                except Exception as e:
                    failed += 1
                    logger.error(f"Failed to process order KPI {order_data.get('order_id')}: {e}")
            
            session.commit()
            
        logger.info(f"Background order KPI processing completed: "
                   f"processed={processed}, failed={failed}")
        
    except Exception as e:
        logger.error(f"Background order KPI processing failed: {e}", exc_info=True)

