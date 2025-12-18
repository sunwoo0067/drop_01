import logging
import uuid
import json
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import Product, BenchmarkProduct
from app.services.gemini_utils import optimize_seo
from app.services.image_processing import image_processing_service

logger = logging.getLogger(__name__)

class ProcessingService:
    def __init__(self, db: Session):
        self.db = db

    def process_product(self, product_id: uuid.UUID, min_images_required: int = 5) -> bool:
        """
        Orchestrates the processing of a single product.
        1. Fetch Product details (and related raw data for HTML).
        2. Optimize Name (SEO) using Detail analysis.
        3. Process Images (Hash Breaking + Supabase Upload + Min count).
        4. Update Product record.
        """
        try:
            logger.info(f"Starting processing for product {product_id}...")
            
            # 1. Fetch Product
            product = self.db.scalars(select(Product).where(Product.id == product_id)).one_or_none()
            if not product:
                logger.error(f"Product {product_id} not found.")
                return False

            product.processing_status = "PROCESSING"
            self.db.commit()
                
            # We need detail_html and raw images. 
            # In current schema, Product links to SupplierItemRaw via supplier_item_id.
            # We need to fetch SupplierItemRaw to get more context if mapped, 
            # OR we check BenchmarkProduct if this product came from there?
            # Assuming Product created from SupplierItemRaw.
            
            detail_text = ""
            raw_image_urls = []
            
            if product.supplier_item_id:
                from app.models import SupplierItemRaw
                raw_item = self.db.scalars(select(SupplierItemRaw).where(SupplierItemRaw.id == product.supplier_item_id)).one_or_none()
                if raw_item and raw_item.raw:
                    # Parse OwnerClan specific raw structure
                    # detail_html usually in "content" or "description"
                    detail_text = raw_item.raw.get("content") or raw_item.raw.get("description") or ""
                    # images usually in "obs_images", "images", or extracted from detailed page
                    raw_image_urls = []
                    # Try to find images in raw data - strict implementation depends on source
                    # For now, let's look for known keys or fallback to empty to trigger extraction
                    if "images" in raw_item.raw:
                         raw_image_urls = raw_item.raw["images"]
            
            # Fallback text if detail_text empty
            if not detail_text and product.description:
                detail_text = product.description

            # 2. Optimize Name
            # Extract basic keywords from title or brand
            initial_keywords = [product.brand] if product.brand else []
            seo_result = optimize_seo(product.name, initial_keywords, detail_text=detail_text)
            
            new_title = seo_result.get("title", product.name)
            new_tags = seo_result.get("tags", [])
            
            # 3. Process Images
            # If no raw images found, we pass empty list. 
            # The service will try to extract from detail_text if count < 5.
            # However, if we have NO images to start with, extraction is critical.
            
            processed_urls = image_processing_service.process_and_upload_images(
                image_urls=raw_image_urls,
                detail_html=detail_text,
                product_id=str(product.id)
            )
            
            # 4. Update Product
            product.processed_name = new_title
            product.processed_keywords = new_tags
            product.processed_image_urls = processed_urls
            
            if processed_urls and len(processed_urls) >= max(1, int(min_images_required)) and new_title:
                product.processing_status = "COMPLETED"
            else:
                product.processing_status = "FAILED"
                
            self.db.commit()
            logger.info(f"Successfully processed product {product_id}. Status: {product.processing_status}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing product {product_id}: {e}")
            self.db.rollback()
            try:
                # Try to key status as failed
                product.processing_status = "FAILED"
                self.db.commit()
            except:
                pass
            return False

    def process_pending_products(self, limit: int = 10, min_images_required: int = 5):
        """
        Finds pending products and processes them.
        """
        stmt = select(Product).where(Product.processing_status == "PENDING").limit(limit)
        products = self.db.scalars(stmt).all()
        
        count = 0
        for p in products:
            if self.process_product(p.id, min_images_required=min_images_required):
                count += 1
        return count
