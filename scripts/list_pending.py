from app.session_factory import session_factory
from app.models import SourcingCandidate
from sqlalchemy import select

def main():
    with session_factory() as s:
        candidates = s.execute(select(SourcingCandidate).where(SourcingCandidate.status == 'PENDING')).scalars().all()
        print(f"Total Pending: {len(candidates)}")
        for i, c in enumerate(candidates):
            print(f"{i+1}. {c.name}")

if __name__ == "__main__":
    main()
