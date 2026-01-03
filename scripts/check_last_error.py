from app.session_factory import session_factory
from app.models import SupplierRawFetchLog
from sqlalchemy import select

with session_factory() as session:
    stmt = (
        select(SupplierRawFetchLog)
        .where(SupplierRawFetchLog.endpoint.like("%products%"))
        .order_by(SupplierRawFetchLog.fetched_at.desc())
        .limit(5)
    )
    logs = session.execute(stmt).scalars().all()
    for log in logs:
        print(f"[{log.fetched_at}] Endpoint: {log.endpoint}, Status: {log.http_status}")
        if log.response_payload:
            print(f"Response: {log.response_payload}")
