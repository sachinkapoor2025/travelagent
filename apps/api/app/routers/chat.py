"""Web chat agent endpoints."""

from typing import Optional

from fastapi import APIRouter, Header

from app.schemas import ChatMessageRequest, ChatMessageResponse
from app.services.chat import chat_agent

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatMessageResponse)
async def chat(
    payload: ChatMessageRequest,
    x_referral_code: Optional[str] = Header(None, alias="X-Referral-Code"),
) -> ChatMessageResponse:
    result = await chat_agent.chat(
        message=payload.message,
        session_id=payload.session_id,
        phone=payload.phone,
        referral_code=x_referral_code or payload.referral_code,
    )
    return ChatMessageResponse(**result)


@router.get("/widget.js")
async def chat_widget_script() -> str:
    return """
(function(){
  var s = document.createElement('script');
  s.src = '/api/v1/chat/widget-loader.js';
  document.head.appendChild(s);
})();
"""
