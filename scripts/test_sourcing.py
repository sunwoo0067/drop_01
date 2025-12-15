import httpx
import asyncio

BASE_URL = "http://localhost:8888"

async def test_sourcing():
    async with httpx.AsyncClient() as client:
        # 1. Health Check
        resp = await client.get(f"{BASE_URL}/health")
        print(f"Health: {resp.status_code}")
        if resp.status_code != 200:
            print("Server is not healthy")
            return

        # 2. Trigger Keyword Sourcing
        payload = {"keywords": ["camping chair", "tent"], "min_margin": 0.2}
        resp = await client.post(f"{BASE_URL}/api/sourcing/keyword", json=payload)
        print(f"Keyword Sourcing: {resp.status_code} - {resp.json()}")

if __name__ == "__main__":
    asyncio.run(test_sourcing())
