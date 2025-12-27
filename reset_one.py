from app.db import get_session
from app.models import Product, MarketListing, MarketAccount
from sqlalchemy import update, select

db = next(get_session())
try:
    naver_acc = db.execute(select(MarketAccount.id).where(MarketAccount.market_code == 'SMARTSTORE')).scalars().all()
    listed_ids = db.execute(select(MarketListing.product_id).where(MarketListing.market_account_id.in_(naver_acc))).scalars().all()
    
    target_id = db.execute(select(Product.id).where(Product.id.notin_(listed_ids)).limit(1)).scalar()
    if target_id:
        db.execute(update(Product).where(Product.id == target_id).values(processing_status='COMPLETED', processed_image_urls=None))
        db.commit()
        print(f'Target {target_id} reset to COMPLETED')
finally:
    db.close()
