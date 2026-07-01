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
        email=payload.email,
        referral_code=x_referral_code or payload.referral_code,
    )
    return ChatMessageResponse(**result)


@router.get("/widget.js")
async def chat_widget_script() -> str:
    return """
(function(){
  var s = document.createElement('script');
  s.src = (window.__TRAVELAI__ && window.__TRAVELAI__.apiBase ? window.__TRAVELAI__.apiBase.replace('/api/v1','') : '') + '/api/v1/chat/widget-loader.js';
  document.head.appendChild(s);
})();
"""


@router.get("/widget-loader.js")
async def chat_widget_loader() -> str:
    api = "/api/v1/chat"
    return f"""
(function() {{
  var box = document.createElement('div');
  box.id = 'travelai-chat-widget';
  box.innerHTML = '<div style="position:fixed;bottom:20px;right:20px;z-index:9999;font-family:sans-serif"><div id="ta-chat-panel" style="display:none;width:320px;height:400px;background:#fff;border:1px solid #ddd;border-radius:12px;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.15)"><div style="background:#2563eb;color:#fff;padding:10px;font-weight:600">Sarah AI</div><div id="ta-msgs" style="height:300px;overflow-y:auto;padding:10px;font-size:13px"></div><form id="ta-form" style="display:flex;border-top:1px solid #eee"><input id="ta-input" placeholder="Ask about travel..." style="flex:1;border:none;padding:8px" /><button style="background:#2563eb;color:#fff;border:none;padding:8px 12px">Send</button></form></div><button id="ta-toggle" style="width:56px;height:56px;border-radius:50%;background:#2563eb;color:#fff;border:none;font-size:24px;cursor:pointer">✈</button></div>';
  document.body.appendChild(box);
  var sid = null;
  document.getElementById('ta-toggle').onclick = function() {{
    var p = document.getElementById('ta-chat-panel');
    p.style.display = p.style.display === 'none' ? 'block' : 'none';
  }};
  document.getElementById('ta-form').onsubmit = async function(e) {{
    e.preventDefault();
    var input = document.getElementById('ta-input');
    var msg = input.value;
    if (!msg) return;
    document.getElementById('ta-msgs').innerHTML += '<div><b>You:</b> '+msg+'</div>';
    input.value = '';
    var r = await fetch('{api}', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{message:msg,session_id:sid}})}});
    var d = await r.json();
    sid = d.session_id;
    document.getElementById('ta-msgs').innerHTML += '<div style="color:#2563eb"><b>Sarah:</b> '+d.reply+'</div>';
  }};
}})();
"""

