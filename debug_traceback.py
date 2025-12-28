
import asyncio
import traceback
from demo_combination_upload import run_demo_sourcing

async def main():
    try:
        await run_demo_sourcing()
    except Exception:
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
