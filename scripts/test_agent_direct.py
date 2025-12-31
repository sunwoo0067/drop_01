import asyncio
import logging
from app.db import SessionLocal
from app.services.ai.agents.cs_workflow_agent import CSWorkflowAgent

async def test_direct():
    print("Starting direct agent test...")
    db = SessionLocal()
    agent = CSWorkflowAgent(db)
    
    input_data = {
        "inquiry_id": 999999, # Dummy ID for testing loopback
        "content": "이 상품 전압이 어떻게 되나요? 220v인가요?",
        "market_code": "COUPANG",
        "product_info": {"name": "테스트 멀티탭", "description": "220v 한국 전용"}
    }
    
    print("Running agent...")
    try:
        # Note: finalize will fail to DB update if ID 999999 doesn't exist, 
        # but we can see the logs before that.
        result = await agent.run_cs(input_data)
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_direct())
