import asyncio
import logging
import sys
import os

# 프로젝트 루트 디렉토리를 path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.services.shadow_sync_service import ShadowSyncService

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("shadow_sync_trigger")

async def main():
    logger.info("=" * 50)
    logger.info("🚀 Shadow Mode Inquiry Sync & AI Processing Trigger")
    logger.info("=" * 50)
    
    session = SessionLocal()
    try:
        service = ShadowSyncService(session)
        logger.info("Checking active market accounts and fetching live inquiries...")
        
        # 실제 마켓 API 연동 및 문의 수집 시작
        counts = await service.sync_all_markets()
        
        logger.info("-" * 50)
        logger.info("📊 Shadow Sync Summary:")
        total = 0
        for market, count in counts.items():
            logger.info(f"   • {market}: {count} inquiries newly ingested")
            total += count
        
        if total == 0:
            logger.info("ℹ️ No new unanswered inquiries found on markets.")
        else:
            logger.info(f"✅ Successfully processed {total} inquiries in Shadow Mode.")
            logger.info("   (Check MarketInquiryRaw table for details and AI drafts)")
        
        logger.info("-" * 50)
        logger.info("Shadow Mode synchronization process completed.")
        
    except Exception as e:
        logger.error(f"❌ Critical error during shadow sync: {e}", exc_info=True)
    finally:
        session.close()
        logger.info("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
