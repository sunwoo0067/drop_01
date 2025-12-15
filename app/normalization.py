import logging
import uuid
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import SupplierItemRaw, Product

logger = logging.getLogger(__name__)

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
        item_name = data.get("item_name") or data.get("name") or "Untitled"
        supply_price = data.get("supply_price") or 0
        brand_name = data.get("brand") or data.get("brand_name")
        description = data.get("description") or data.get("content")
        
        # Calculate Selling Price (Simple Logic: Cost * 1.2)
        try:
            cost = int(float(supply_price))
        except (ValueError, TypeError):
            cost = 0
            
        selling_price = int(cost * 1.2)
        
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
