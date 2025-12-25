from app.session_factory import session_factory
from app.models import OrchestrationEvent
from sqlalchemy import select

with session_factory() as session:
    stmt = select(OrchestrationEvent).order_by(OrchestrationEvent.created_at.desc()).limit(20)
    events = session.execute(stmt).scalars().all()
    for e in events:
        print(f"[{e.created_at}] Step: {e.step}, Status: {e.status}, Message: {e.message}")
