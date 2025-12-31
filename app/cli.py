import argparse
import sys
import logging
import asyncio
from typing import Optional

from app.db import get_session
from app.ownerclan_sync import run_ownerclan_job
from app.models import MarketAccount

# 로그 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("app.cli")

def run_sync_command(args):
    """동기화 명령 실행기"""
    session = next(get_session())
    try:
        vendor = args.vendor
        channel = args.channel
        
        # 1. OwnerClan Items (Legacy/Hardened)
        if args.job_type == "ownerclan_items_raw" or (vendor == "ownerclan" and channel == "items"):
            logger.info("[CLI] Starting OwnerClan Item Sync")
            run_ownerclan_job(
                use_handler=args.use_handler,
                batch_commit_size=args.batch_commit_size
            )
            return

        # 2. Coupang Orders (Phase 1)
        if vendor == "coupang" and channel == "orders":
            from app.sync.coupang_order_sync import CoupangOrderSync
            logger.info("[CLI] Starting Coupang Order Sync")
            accounts = session.query(MarketAccount).filter_by(market_code="COUPANG", is_active=True).all()
            for acc in accounts:
                logger.info(f"[CLI] Account: {acc.name}")
                CoupangOrderSync(session, acc).run()
            return

        # 3. Coupang QnA (Phase 2)
        if vendor == "coupang" and channel == "qna":
            from app.sync.coupang_qna_sync import CoupangQnaSync
            logger.info("[CLI] Starting Coupang QnA Sync")
            accounts = session.query(MarketAccount).filter_by(market_code="COUPANG", is_active=True).all()
            for acc in accounts:
                logger.info(f"[CLI] Account: {acc.name}")
                CoupangQnaSync(session, acc).run()
            return

        # 4. Naver Orders (PR-7)
        if vendor == "naver" and channel == "orders":
            from app.sync.naver_order_sync import NaverOrderSync
            logger.info("[CLI] Starting Naver Order Sync")
            accounts = session.query(MarketAccount).filter_by(market_code="NAVER", is_active=True).all()
            for acc in accounts:
                logger.info(f"[CLI] Account: {acc.name}")
                NaverOrderSync(session, acc).run()
            return

        # 5. Naver QnA (PR-7)
        if vendor == "naver" and channel == "qna":
            from app.sync.naver_qna_sync import NaverQnaSync
            logger.info("[CLI] Starting Naver QnA Sync")
            accounts = session.query(MarketAccount).filter_by(market_code="NAVER", is_active=True).all()
            for acc in accounts:
                logger.info(f"[CLI] Account: {acc.name}")
                NaverQnaSync(session, acc).run()
            return

        # 6. CSAgent (PR-7 Beta)
        if vendor == "ai" and channel == "cs-agent":
            from app.services.agents.cs_agent import CSAgent
            logger.info("[CLI] Starting CSAgent Draft Generation")
            agent = CSAgent(session)
            asyncio.run(agent.process_pending_threads())
            return

        # 7. Pricing & Profit Scan (PR-8)
        if vendor == "pricing" and channel == "scan":
            from app.services.pricing.profit_guard import ProfitGuard
            from app.services.pricing.recommender import PricingRecommender
            from app.services.pricing.enforcer import PriceEnforcer
            from app.models import Product, MarketListing, MarketAccount

            logger.info("[CLI] Starting Pricing & Profit Scan")
            
            guard = ProfitGuard(session)
            recommender = PricingRecommender(session)
            enforcer = PriceEnforcer(session)

            # 모든 활성 리스팅 대상
            listings = session.query(MarketListing).join(MarketAccount).filter(
                MarketListing.status == "ACTIVE"
            ).all()

            for listing in listings:
                prod = session.query(Product).filter_by(id=listing.product_id).first()
                if not prod: continue

                # 1단계: 수익 분석
                snapshot = guard.analyze_product(prod.id, listing.market_account.market_code, prod.selling_price)
                guard.save_snapshot(snapshot)

                # 2단계: 가격 권고
                rec = recommender.recommend_for_product(
                    prod.id,
                    listing.market_account.market_code,
                    listing.market_account_id,
                    prod.selling_price
                )
                if rec:
                    session.add(rec)

            session.commit()

            # 3단계: 자동 집행 시뮬레이션 (Mode에 따라 동작)
            mode = getattr(args, "mode", "SHADOW")
            asyncio.run(enforcer.process_recommendations(mode=mode))
            return

        # 8. Analytics ETL (PR-9)
        if vendor == "analytics" and channel == "etl":
            from app.services.analytics.etl_manager import ETLManager
            logger.info("[CLI] Starting Analytics ETL")
            etl = ETLManager(session)
            etl.sync_all()
            return

        logger.error(f"[CLI] Unsupported configuration: vendor={vendor}, channel={channel}")
        sys.exit(1)

    except Exception as e:
        logger.exception(f"[CLI] Critical error: {e}")
        sys.exit(1)
    finally:
        session.close()

def main():
    parser = argparse.ArgumentParser(description="Drop_01 Operations CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    sync_parser = subparsers.add_parser("run-sync", help="Run synchronization jobs")
    sync_parser.add_argument("--vendor", choices=["ownerclan", "coupang", "naver", "ai", "pricing"], default="ownerclan")
    sync_parser.add_argument("--channel", choices=["items", "orders", "qna", "cs-agent", "scan", "etl"], default="items")
    sync_parser.add_argument("--mode", choices=["SHADOW", "ENFORCE", "ENFORCE_LITE"], default="SHADOW", help="Execution mode for pricing (SHADOW, ENFORCE, ENFORCE_LITE)")
    sync_parser.add_argument("--job-type", help="Legacy job type identifier")
    sync_parser.add_argument("--use-handler", action="store_true")
    sync_parser.add_argument("--batch-commit-size", type=int, default=200)

    args = parser.parse_args()

    if args.command == "run-sync":
        run_sync_command(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
