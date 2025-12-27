import logging
import uuid
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.session_factory import session_factory
from app.models import MarketAccount, SupplierAccount
from app.smartstore_client import SmartStoreClient
from app.coupang_client import CoupangClient
from app.ownerclan_client import OwnerClanClient
from app.settings import settings
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_market_accounts():
    print("\n=== Market Account Verification ===")
    with session_factory() as session:
        accounts = session.execute(select(MarketAccount)).scalars().all()
        if not accounts:
            print("No market accounts found in DB.")
            return

        for account in accounts:
            print(f"\nChecking Account: {account.name} (Code: {account.market_code}, ID: {account.id})")
            creds = account.credentials
            if not creds:
                print(" [ERROR] No credentials found in DB.")
                continue

            try:
                if account.market_code == "SMARTSTORE":
                    client_id = creds.get("client_id")
                    client_secret = creds.get("client_secret")
                    if not client_id or not client_secret:
                        print(f" [ERROR] Missing client_id or client_secret in credentials: {list(creds.keys())}")
                        continue
                    
                    client = SmartStoreClient(client_id, client_secret)
                    status, data = client.get_products(size=1)
                    if status == 200:
                        print(f" [SUCCESS] Connection verified. Products count: {data.get('totalCount', 0)}")
                    else:
                        print(f" [FAILURE] API error (HTTP {status}): {data.get('message', 'Unknown error')}")

                elif account.market_code == "COUPANG":
                    access_key = creds.get("access_key")
                    secret_key = creds.get("secret_key")
                    vendor_id = creds.get("vendor_id")
                    if not access_key or not secret_key or not vendor_id:
                        print(f" [ERROR] Missing Coupang credentials: {list(creds.keys())}")
                        continue
                    
                    client = CoupangClient(access_key, secret_key, vendor_id)
                    # Simple test: get seller info or categories
                    # get_products(size=1) is also okay
                    status, data = client.get_products(max_per_page=1)
                    if status == 200:
                        print(f" [SUCCESS] Connection verified.")
                    else:
                        print(f" [FAILURE] API error (HTTP {status}): {data}")
                else:
                    print(f" [WARNING] Unknown market code: {account.market_code}")

            except Exception as e:
                print(f" [ERROR] Exception during verification: {e}")

def verify_supplier_accounts():
    print("\n=== Supplier Account Verification ===")
    with session_factory() as session:
        accounts = session.execute(select(SupplierAccount)).scalars().all()
        if not accounts:
            print("No supplier accounts found in DB.")
            return

        for account in accounts:
            print(f"\nChecking Supplier: {account.username} (Code: {account.supplier_code}, ID: {account.id})")
            if account.supplier_code == "ownerclan":
                try:
                    client = OwnerClanClient(
                        auth_url=settings.ownerclan_auth_url,
                        api_base_url=settings.ownerclan_api_base_url,
                        graphql_url=settings.ownerclan_graphql_url
                    )
                    
                    # OwnerClan usually requires an access token, which is stored in access_token field
                    # or we can issue a new one using username/credentials
                    token = account.access_token
                    if not token:
                        print(" [INFO] No access token found, attempting to issue new one...")
                        creds = account.credentials or {}
                        password = creds.get("password") or settings.ownerclan_primary_password
                        if not password:
                            print(" [ERROR] No password found for OwnerClan")
                            continue
                        
                        token_obj = client.issue_token(account.username, password, account.user_type)
                        token = token_obj.access_token
                        print(" [SUCCESS] Issued new token.")
                    
                    client = client.with_token(token)
                    status, data = client.get_products(limit=1)
                    if status == 200:
                        print(f" [SUCCESS] Connection verified. Found {len(data.get('items', []))} items (REST/GQL).")
                    else:
                        print(f" [FAILURE] API error (HTTP {status}): {data}")
                except Exception as e:
                    print(f" [ERROR] Exception during verification: {e}")
            else:
                print(f" [WARNING] Unknown supplier code: {account.supplier_code}")

if __name__ == "__main__":
    verify_market_accounts()
    verify_supplier_accounts()
