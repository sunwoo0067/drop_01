
from app.db import SessionLocal
from app.models import OrchestrationEvent
from sqlalchemy import select

def check_events():
    with SessionLocal() as session:
        stmt = select(OrchestrationEvent).order_by(OrchestrationEvent.created_at.desc()).limit(20)
        events = session.scalars(stmt).all()
        
        print(f"{'Time':<20} | {'Step':<12} | {'Status':<10} | {'Message'}")
        print("-" * 100)
        
        for e in events:
            print(f"{e.created_at.isoformat() if e.created_at else 'None':<20} | {e.step:<12} | {e.status:<10} | {e.message}")
            if e.details:
                print(f"  Details: {e.details}")

if __name__ == "__main__":
    check_events()
