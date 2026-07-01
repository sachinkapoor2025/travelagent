"""B2B lead miner — travel agencies & directory listings worldwide."""

from __future__ import annotations

from typing import Any

from app.services.lead_segment import apply_segment
from app.services.miners.directories import mine_directories_batch


async def mine_b2b(cursor: int = 0, batch_size: int = 150) -> tuple[list[dict[str, Any]], int, bool, int]:
    """Fetch B2B directory leads for a batch of global markets."""
    raw, next_cursor, complete, total_markets = await mine_directories_batch(
        cursor=cursor,
        import_limit=batch_size,
    )
    leads = [apply_segment(lead, default="b2b") for lead in raw]
    return leads, next_cursor, complete, total_markets
