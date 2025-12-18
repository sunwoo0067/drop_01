from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime
import uuid

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
    
    model_config = ConfigDict(from_attributes=True)
