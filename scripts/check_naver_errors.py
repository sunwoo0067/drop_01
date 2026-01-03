from app.session_factory import session_factory
from app.models import SupplierRawFetchLog
from sqlalchemy import select

with session_factory() as session:
    stmt = (
        select(SupplierRawFetchLog)
        .where(SupplierRawFetchLog.supplier_code == "smartstore")
        .order_by(SupplierRawFetchLog.fetched_at.desc())
        .limit(10)
    )
    logs = session.execute(stmt).scalars().all()
    for log in logs:
        print(f"[{log.fetched_at}] Endpoint: {log.endpoint}, Status: {log.http_status}")
        if log.http_status != 200:
            print(f"Request: {log.request_payload}")
            print(f"Response: {log.response_payload}")
