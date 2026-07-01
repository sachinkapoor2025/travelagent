"""Background worker — uses DynamoDB lead repo."""

import asyncio
import logging

from app.config import get_settings
from app.services.worker_jobs import process_hot_leads
from app.services.session import session_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("travel-ai-worker")
settings = get_settings()


async def run_worker() -> None:
    await session_store.connect()
    logger.info("TravelAI worker started (DynamoDB)")
    while True:
        try:
            result = await process_hot_leads()
            logger.info("Worker cycle: %s", result)
        except Exception:
            logger.exception("Worker cycle failed")
        await asyncio.sleep(120)


if __name__ == "__main__":
    asyncio.run(run_worker())
