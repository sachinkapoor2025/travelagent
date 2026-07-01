"""MCP-compatible server endpoints for external AI agents."""

from typing import Any

from app.routers.auth import admin_required
from fastapi import APIRouter, HTTPException

from app.services.mcp_server import mcp_server

router = APIRouter(dependencies=[admin_required()], prefix="/mcp", tags=["mcp"])


@router.get("/tools")
async def list_mcp_tools() -> dict[str, Any]:
    return mcp_server.list_tools()


@router.post("/tools/call")
async def call_mcp_tool(payload: dict[str, Any]) -> dict[str, Any]:
    name = payload.get("name") or payload.get("tool")
    arguments = payload.get("arguments") or payload.get("params") or {}
    if not name:
        raise HTTPException(status_code=400, detail="Tool name required")
    return await mcp_server.call_tool(name, arguments)


@router.post("/agentic/book")
async def agentic_book(payload: dict[str, Any]) -> dict[str, Any]:
    from app.models import Market
    from app.services.agentic_booking import agentic_booking

    session_id = await agentic_booking.create_session(
        phone=payload.get("phone"),
        market=Market(payload.get("market", "uae")),
    )
    return await agentic_booking.run_booking_loop(
        session_id,
        payload["origin"].upper(),
        payload["destination"].upper(),
        payload["departure_date"],
        payload.get("passengers", 1),
        phone=payload.get("phone"),
        market=Market(payload.get("market", "uae")),
    )
