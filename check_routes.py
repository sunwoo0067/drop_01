from app.api.endpoints.settings import router
import uuid

print("Listing all routes in settings router:")
for route in router.routes:
    print(f"Path: {route.path}, Methods: {route.methods}")

print("\nVerifying if /markets/smartstore/accounts exists...")
found = False
for route in router.routes:
    if "/markets/smartstore/accounts" in route.path:
        print(f"FOUND: {route.path} with methods {route.methods}")
        found = True

if not found:
    print("NOT FOUND: /markets/smartstore/accounts")
