import asyncio
import json
import logging
from app.services.ai.service import AIService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_planning():
    ai = AIService()
    print("\n--- Generating Seasonal Strategy (Current Date) ---")
    strategy = await ai.plan_seasonal_strategy()
    
    print(json.dumps(strategy, indent=2, ensure_ascii=False))
    
    target_keywords = strategy.get("target_keywords", [])
    out_dated_keywords = strategy.get("out_dated_keywords", [])
    upcoming_events = strategy.get("upcoming_events", [])
    
    christmas_present = False
    for kw in target_keywords + upcoming_events:
        if "크리스마스" in kw or "Christmas" in kw or "성탄절" in kw:
            christmas_present = True
            break
            
    if christmas_present:
        print("\n❌ FAILED: Found past event keywords in target/upcoming lists.")
    else:
        print("\n✅ SUCCESS: Past event keywords (Christmas) are excluded from active targets.")

    outdated_check = False
    for kw in out_dated_keywords:
        if "크리스마스" in kw or "Christmas" in kw or "성탄절" in kw:
            outdated_check = True
            break
            
    if outdated_check:
        print("✅ SUCCESS: Christmas is correctly identified as an out-dated keyword.")
    else:
        print("⚠️ WARNING: Christmas was not explicitly listed in out-dated keywords (might be okay if other past events were).")

if __name__ == "__main__":
    asyncio.run(test_planning())
