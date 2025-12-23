import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_session
from app.models import MarketAccount
from sqlalchemy import select

client = TestClient(app)

def test_deletion():
    # 1. Create a dummy account directly for testing deletion
    with next(get_session()) as session:
        acc = MarketAccount(
            market_code="COUPANG",
            name="TEST_DELETE_ACCOUNT",
            credentials={"vendor_id": "TEST", "vendor_user_id": "TEST", "access_key": "TEST", "secret_key": "TEST"},
            is_active=False
        )
        session.add(acc)
        session.commit()
        acc_id = str(acc.id)
        print(f"Created test account: {acc_id}")

    # 2. Call the delete API
    response = client.delete(f"/api/settings/markets/coupang/accounts/{acc_id}")
    print(f"Delete API Response: {response.status_code}, {response.json()}")
    assert response.status_code == 200
    assert response.json()["deleted"] is True

    # 3. Verify it's gone from DB
    with next(get_session()) as session:
        stmt = select(MarketAccount).where(MarketAccount.id == uuid.UUID(acc_id))
        deleted_acc = session.execute(stmt).scalar_one_or_none()
        if deleted_acc is None:
            print("Verification Success: Account is deleted from DB.")
        else:
            print("Verification Failure: Account still exists in DB.")

if __name__ == "__main__":
    test_deletion()
