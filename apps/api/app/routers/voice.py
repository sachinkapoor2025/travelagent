"""Vapi voice webhook and assistant configuration."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import Call, CallDirection, Market
from app.services.session import session_store
from app.services.voice import get_vapi_assistant_config, handle_tool_call, map_language

router = APIRouter(prefix="/voice", tags=["voice"])
settings = get_settings()


@router.get("/assistant-config")
async def assistant_config(request: Request) -> dict[str, Any]:
    base_url = str(request.base_url).rstrip("/")
    return get_vapi_assistant_config(base_url)


@router.post("/webhook")
async def vapi_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    payload = await request.json()
    message = payload.get("message", {})
    msg_type = message.get("type")

    if msg_type == "tool-calls":
        return await _handle_tool_calls(message)

    if msg_type == "end-of-call-report":
        return await _handle_end_of_call(message, db)

    if msg_type == "status-update":
        return {"status": "received"}

    return {"status": "ignored", "type": msg_type}


async def _handle_tool_calls(message: dict[str, Any]) -> dict[str, Any]:
    tool_calls = message.get("toolCallList", [])
    results = []

    call = message.get("call", {})
    session_id = (
        call.get("assistantOverrides", {}).get("variableValues", {}).get("session_id")
        or call.get("id", "unknown")
    )

    for tool_call in tool_calls:
        function = tool_call.get("function", {})
        tool_name = function.get("name", "")
        args = function.get("arguments", {})
        if isinstance(args, str):
            import json
            args = json.loads(args)

        result = await handle_tool_call(session_id, tool_name, args)
        results.append({"toolCallId": tool_call.get("id"), "result": result})

    return {"results": results}


async def _handle_end_of_call(message: dict[str, Any], db: AsyncSession) -> dict[str, Any]:
    call_data = message.get("call", {})
    artifact = message.get("artifact", {})

    phone_to = call_data.get("customer", {}).get("number", "")
    phone_from = call_data.get("phoneNumber", {}).get("number", "")
    direction = CallDirection.INBOUND if call_data.get("type") == "inboundPhoneCall" else CallDirection.OUTBOUND

    session_id = call_data.get("assistantOverrides", {}).get("variableValues", {}).get("session_id", call_data.get("id"))
    session = await session_store.get(session_id)

    call = Call(
        external_call_id=call_data.get("id"),
        direction=direction,
        phone_from=phone_from or "",
        phone_to=phone_to or "",
        market=Market(session.get("market", "uae")),
        language=map_language(session.get("language")),
        duration_seconds=call_data.get("duration"),
        transcript=artifact.get("transcript"),
        recording_url=artifact.get("recordingUrl"),
        outcome=message.get("analysis", {}).get("summary"),
        session_data=session,
    )
    db.add(call)
    await db.flush()
    return {"status": "call_logged", "call_id": str(call.id)}
