from __future__ import annotations

import asyncio

from backend.common.background_jobs import background_job_manager


async def main() -> None:
    await background_job_manager.start()
    try:
        while True:
            await asyncio.sleep(60)
    finally:
        await background_job_manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
