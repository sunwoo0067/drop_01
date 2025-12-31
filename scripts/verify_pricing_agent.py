import asyncio
import os
import sys
import uuid
from sqlalchemy.orm import Session

# 프로젝트 루트 디렉토리를 sys.path에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import SessionLocal
from app.services.ai.agents.pricing_agent import PricingAgent
from app.models import MarketListing, Product

async def verify_pricing():
    db = SessionLocal()
    try:
        # 테스트용 리스팅 조회 (첫 번째 리스팅 사용)
        listing = db.query(MarketListing).first()
        if not listing:
            print("No MarketListing found in database. Please run a sync or add sample data.")
            return

        product = db.get(Product, listing.product_id)
        if not product:
            print("Product not found.")
            return

        print(f"--- PricingAgent Verification ---")
        print(f"Target Listing ID: {listing.id}")
        print(f"Product Name: {product.name}")
        print(f"Current Price: {product.selling_price}")
        print(f"Supply Price: {product.cost_price}")
        
        agent = PricingAgent(db)
        
        # 에이전트 실행
        # input_data는 초기화에 사용됨
        input_data = {
            "product_name": product.name,
            "target_roi": 0.20 # 20% 목표
        }
        
        print("\nRunning Agent...")
        result = await agent.run(str(listing.id), input_data, verbose=True)
        
        print("\n--- Execution Result ---")
        print(f"Status: {result.status}")
        
        if result.status == "COMPLETED":
            final_output = result.final_output
            print(f"Suggested Price: {final_output['suggested_price']}원")
            print(f"Strategy: {final_output['strategy']}")
            print(f"Expected ROI: {final_output['expected_roi'] * 100:.2f}%")
            print(f"Reasoning: {final_output['reasoning']}")
        else:
            print(f"Error: {result.error_message}")
            
        print("\nStep Sequence:")
        for step in result.steps:
            print(f"- {step.step_name}: {step.status} ({step.duration_ms:.2f}ms)")

    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(verify_pricing())
