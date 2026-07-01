"""Analytics — DynamoDB."""

from collections import Counter

from app.config import get_settings
from app.services.leads import classify_lead
from app.storage.dynamo import events_store, leads_store

settings = get_settings()


class AnalyticsService:
    async def dashboard_stats(self) -> dict:
        all_leads = leads_store().query_gsi1("LEADS", limit=500)
        leads = [
            {
                "score": int(l.get("score", 0)),
                "status": l.get("status", "new"),
                "source": l.get("source", "unknown"),
                "market": l.get("market", "unknown"),
            }
            for l in all_leads
        ]

        hot = [l for l in leads if classify_lead(l["score"]) == "hot"]
        warm = [l for l in leads if classify_lead(l["score"]) == "warm"]
        by_source = Counter(l["source"] for l in leads)
        by_market = Counter(l["market"] for l in leads)
        by_status = Counter(l["status"] for l in leads)
        total = len(leads)
        contacted = sum(1 for l in leads if l["status"] in {"contacted", "qualified", "quoted", "won"})
        won = sum(1 for l in leads if l["status"] == "won")

        recent_events = events_store().query_gsi1("ANALYTICS", limit=200)
        chat_events = [e for e in recent_events if e.get("event_type") == "chat_message"]

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
            "chat_sessions_24h": len(chat_events),
            "channels": {
                "voice": by_source.get("voice_outbound", 0) + by_source.get("voice_inbound", 0),
                "whatsapp": by_source.get("whatsapp", 0),
                "web": by_source.get("website", 0),
                "meta_ads": by_source.get("meta_ads", 0),
                "google_ads": by_source.get("google_ads", 0),
            },
        }


analytics_service = AnalyticsService()
