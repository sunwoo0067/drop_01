import os
import sqlalchemy as sa
from sqlalchemy import text
from dotenv import load_dotenv
import json

load_dotenv()

db_url = os.getenv("DATABASE_URL")
engine = sa.create_engine(db_url)

product_id = '3bf33c2b-b6f0-4cdd-8a39-2b31f9a4448c'

with engine.connect() as conn:
    # 1. Product info
    res = conn.execute(text("SELECT id, name, status, processing_status, coupang_doc_pending, coupang_doc_pending_reason, processed_image_urls FROM products WHERE id = :pid"), {"pid": product_id})
    product = res.mappings().first()
    print("Product Info:", json.dumps(dict(product) if product else {}, default=str, indent=2))

    # 2. Skip logs
    res = conn.execute(text("SELECT id, endpoint, request_payload, response_payload FROM supplier_raw_fetch_log WHERE endpoint = 'register_product_skipped' AND request_payload::text LIKE :pid_text"), {"pid_text": f'%{product_id}%'})
    skip_logs = [dict(r) for r in res.mappings().all()]
    print("Skip Logs:", json.dumps(skip_logs, default=str, indent=2))
