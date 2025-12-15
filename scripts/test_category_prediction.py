import sys
import os
import uuid
from sqlalchemy import select

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.session_factory import session_factory
from app.models import MarketAccount
from app.coupang_client import CoupangClient
from app.coupang_sync import _get_client_for_account

def test_prediction(product_name: str):
    with session_factory() as session:
        # Get first active Coupang account
        stmt = select(MarketAccount).where(MarketAccount.market_code == "COUPANG", MarketAccount.is_active == True)
        account = session.scalars(stmt).first()
        
        if not account:
            print("No active Coupang account found.")
            return

        print(f"Using account: {account.name} ({account.market_code})")
        
        try:
            client = _get_client_for_account(account)
            
            print(f"Predicting category for: '{product_name}'")
            code, data = client.predict_category(product_name)
            
            print(f"Response Code: {code}")
            print(f"Response Data: {data}")
            
            if code == 200 and data.get("data"):
                 print("Prediction Success!")
                 # Check structure
                 # Usually data['data'] contains 'predictedCategoryCode' or similar
                 # Let's inspect the output to be sure.
            else:
                 print("Prediction Failed.")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_name = "나이키 에어포스 1 운동화"
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
    test_prediction(test_name)
