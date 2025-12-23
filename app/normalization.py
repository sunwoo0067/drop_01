import logging
import uuid
import re

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import SupplierItemRaw, Product
from app.settings import settings
from app.services.pricing import calculate_selling_price, parse_int_price, parse_shipping_fee

logger = logging.getLogger(__name__)

def clean_product_name(name: str, brand: str | None = None) -> str:
    """
    Cleans product name by removing noise like [...], (...), 【...】 and duplicates.
    """
    if not name:
        return ""
        
    # 1. Remove brackets and their contents (e.g., [무료배송], (관리번호))
    # Using non-greedy match to avoid over-deletion
    name = re.sub(r'\[.*?\]|\(.*?\)|【.*?】', '', name)
    
    # 2. Remove common marketing noise
    noise_keywords = ["★특가★", "☆특가☆", "■무료배송■", "●특별할인●", "신상품", "인급"]
    for noise in noise_keywords:
        name = name.replace(noise, "")
        
    # 3. Clean up extra spaces
    name = re.sub(r'\s+', ' ', name).strip()
    
    # 4. Remove duplicate brand name if present at the beginning
    if brand:
        brand = brand.strip()
        # "삼성 삼성 TV" -> "삼성 TV"
        parts = name.split()
        if len(parts) > 1 and parts[0] == brand and parts[1] == brand:
            parts.pop(0)
            name = " ".join(parts)
            
    return name

def normalize_supplier_items(session: Session, batch_size: int = 1000, item_ids: list[uuid.UUID] | None = None) -> int:
    """
    Normalizes raw supplier items into Core Product table.
    - Reads from SupplierItemRaw
    - Upserts into Product
    - Default Margin: 20% (1.2x)
    """
    logger.info("Starting normalization of supplier items...")
    
    stmt = select(SupplierItemRaw)
    
    if item_ids:
        stmt = stmt.filter(SupplierItemRaw.id.in_(item_ids))
    else:
        stmt = stmt.limit(batch_size)
        
    raw_items = session.scalars(stmt).all()
    
    processed_count = 0
    
    for raw_item in raw_items:
        data = raw_item.raw
        if not data:
            continue
            
        # Extract Fields (OwnerClan Spec)
        # Fallbacks included for safety
        raw_item_name = data.get("item_name") or data.get("name") or "Untitled"
        brand_name = data.get("brand") or data.get("brand_name")
        
        # Apply cleaning
        item_name = clean_product_name(raw_item_name, brand=brand_name)
        supply_price = (
            data.get("supply_price")
            or data.get("supplyPrice")
            or data.get("fixedPrice")
            or data.get("fixed_price")
            or data.get("price")
            or 0
        )
        brand_name = data.get("brand") or data.get("brand_name")
        description = data.get("description") or data.get("content")
        
        # Calculate Selling Price (Simple Logic: Cost * margin_rate)
        cost = parse_int_price(supply_price)
        shipping_fee = parse_shipping_fee(data)
            
        try:
            margin_rate = float(settings.pricing_default_margin_rate or 0.0)
        except Exception:
            margin_rate = 0.0
        if margin_rate < 0:
            margin_rate = 0.0
        selling_price = calculate_selling_price(
            cost, 
            margin_rate, 
            shipping_fee, 
            market_fee_rate=float(settings.pricing_market_fee_rate or 0.13)
        )
        
        # Check if Product exists for this raw item
        # We need a way to look up Product by supplier_item_id.
        # Since supplier_item_id is a FK in Product, we can query Product.
        
        existing_product = session.query(Product).filter(
            Product.supplier_item_id == raw_item.id
        ).one_or_none()
        
        if existing_product:
            # Update
            existing_product.name = item_name
            existing_product.brand = brand_name
            existing_product.description = description
            existing_product.cost_price = cost
            existing_product.selling_price = selling_price
            # We don't overwrite status if it's already active, unless we want to sync status?
            # Keeping status as is for now, or maybe sync 'SOLD_OUT' if stock=0.
            processed_count += 1
        else:
            # Create
            new_product = Product(
                supplier_item_id=raw_item.id,
                name=item_name,
                brand=brand_name,
                description=description,
                cost_price=cost,
                selling_price=selling_price,
                status="DRAFT"
            )
            session.add(new_product)
            processed_count += 1
            
    session.commit()
    logger.info(f"Normalized {processed_count} items.")
    return processed_count
