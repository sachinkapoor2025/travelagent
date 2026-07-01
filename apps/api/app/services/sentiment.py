"""Call sentiment analysis for hot lead escalation."""

import json
from typing import Any, Optional

from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()


class SentimentService:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def analyze_call(self, transcript: Optional[str], session: dict[str, Any]) -> dict[str, Any]:
        if not transcript:
            return {"sentiment": "neutral", "score": 0.5, "escalate": False, "summary": "No transcript"}

        if self.client:
            try:
                response = await self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "user",
                            "content": f"""Analyze this travel sales call transcript.
Return JSON: {{"sentiment": "positive|neutral|negative", "score": 0-1, "escalate": bool, "summary": str, "intent": str}}

Transcript:
{transcript[:4000]}""",
                        }
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                data = json.loads(response.choices[0].message.content or "{}")
                data["escalate"] = data.get("escalate") or (
                    data.get("sentiment") == "positive" and data.get("score", 0) >= 0.75
                )
                return data
            except Exception:
                pass

        positive_words = {"book", "yes", "confirm", "payment", "today", "urgent", "ready"}
        text = transcript.lower()
        hits = sum(1 for w in positive_words if w in text)
        score = min(0.9, 0.4 + hits * 0.1)
        return {
            "sentiment": "positive" if score >= 0.7 else "neutral",
            "score": score,
            "escalate": score >= 0.75,
            "summary": "Rule-based sentiment from transcript keywords",
            "intent": session.get("destination", "unknown"),
        }


sentiment_service = SentimentService()
