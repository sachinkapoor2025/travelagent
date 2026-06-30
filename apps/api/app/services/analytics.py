"""Analytics and conversion funnel metrics."""

from collections import Counter
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.database import async_session_factory
from app.models import Lead
from app.services.leads import classify_lead
from app.storage.dynamo import events_store, leads_store

settings = get_settings()


class AnalyticsService:
    async def dashboard_stats(self) -> dict[str, Any]:
        if settings.use_dynamo:
            return await self._dynamo_stats()
        return await self._postgres_stats()

    async def _dynamo_stats(self) -> dict[str, Any]:
        leads = leads_store()
        events = events_store()

        all_leads = leads.query_gsi1("LEADS", limit=500)
        hot = [l for l in all_leads if int(l.get("score", 0)) >= settings.lead_hot_score_threshold]
        warm = [
            l
            for l in all_leads
            if settings.lead_warm_score_threshold <= int(l.get("score", 0)) < settings.lead_hot_score_threshold
        ]

        by_source = Counter(l.get("source", "unknown") for l in all_leads)
        by_market = Counter(l.get("market", "unknown") for l in all_leads)
        by_status = Counter(l.get("status", "unknown") for l in all_leads)

        recent_events = events.query_gsi1("ANALYTICS", limit=200) if events.enabled else []
        chat_events = [e for e in recent_events if e.get("event_type") == "chat_message"]

        total = len(all_leads)
        contacted = sum(1 for l in all_leads if l.get("status") in {"contacted", "qualified", "quoted", "won"})
        won = sum(1 for l in all_leads if l.get("status") == "won")

        return self._build_response(total, hot, warm, by_source, by_market, by_status, contacted, won, len(chat_events))

    async def _postgres_stats(self) -> dict[str, Any]:
        async with async_session_factory() as db:
            result = await db.execute(select(Lead))
            all_leads = list(result.scalars().all())

        hot = [l for l in all_leads if classify_lead(l.score) == "hot"]
        warm = [l for l in all_leads if classify_lead(l.score) == "warm"]
        by_source = Counter(l.source.value for l in all_leads)
        by_market = Counter(l.market.value for l in all_leads)
        by_status = Counter(l.status.value for l in all_leads)
        total = len(all_leads)
        contacted = sum(1 for l in all_leads if l.status.value in {"contacted", "qualified", "quoted", "won"})
        won = sum(1 for l in all_leads if l.status.value == "won")

        return self._build_response(total, hot, warm, by_source, by_market, by_status, contacted, won, 0)

    def _build_response(
        self,
        total: int,
        hot: list,
        warm: list,
        by_source: Counter,
        by_market: Counter,
        by_status: Counter,
        contacted: int,
        won: int,
        chat_sessions: int,
    ) -> dict[str, Any]:
        return {
            "total_leads": total,
            "hot_leads": len(hot),
            "warm_leads": len(warm),
            "cold_leads": max(0, total - len(hot) - len(warm)),
            "contact_rate": round(contacted / total * 100, 1) if total else 0,
            "conversion_rate": round(won / total * 100, 1) if total else 0,
            "by_source": dict(by_source),
            "by_market": dict(by_market),
            "by_status": dict(by_status),
            "chat_sessions_24h": chat_sessions,
            "channels": {
                "voice": by_source.get("voice_outbound", 0) + by_source.get("voice_inbound", 0),
                "whatsapp": by_source.get("whatsapp", 0),
                "web": by_source.get("website", 0),
                "meta_ads": by_source.get("meta_ads", 0),
                "google_ads": by_source.get("google_ads", 0),
            },
        }


analytics_service = AnalyticsService()
