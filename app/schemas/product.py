from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime
import uuid
from sqlalchemy.dialects.postgresql import JSONB

class MarketListingResponse(BaseModel):
    id: uuid.UUID
    market_item_id: str
    status: str
    coupang_status: Optional[str] = None
    rejection_reason: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)

class ProductResponse(BaseModel):
    id: uuid.UUID
    name: str
    processed_name: Optional[str] = None
    brand: Optional[str] = None
    selling_price: int
    processing_status: str
    processed_image_urls: Optional[List[str]] = None
    processed_keywords: Optional[List[str]] = None
    status: str
    created_at: datetime
    market_listings: List[MarketListingResponse] = []
    
    model_config = ConfigDict(from_attributes=True)
