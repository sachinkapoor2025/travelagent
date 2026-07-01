"""Internet lead mining — Clay/Apollo webhooks and batch import."""

from typing import Any

from app.services.lead_enrichment import lead_enrichment
from app.services.voice import initiate_outbound_call
from app.storage.dynamo import events_store, now_iso
from app.storage.leads_repo import lead_repo

settings = None


def _settings():
    global settings
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    return settings


class LeadMiningService:
    async def ingest_webhook(self, payload: dict[str, Any], source: str = "clay") -> dict[str, Any]:
        leads_raw = payload.get("leads") or payload.get("records") or [payload]
        imported = 0
        hot_leads: list[dict[str, Any]] = []

        for raw in leads_raw:
            lead_data = self._normalize(raw, source)
            if not lead_data.get("phone"):
                continue
            enriched = await lead_enrichment.enrich(lead_data)
            saved = await lead_repo.create_or_update(enriched)
            imported += 1
            if saved.get("score", 0) >= _settings().lead_hot_score_threshold:
                hot_leads.append(saved)

        events_store().put(
            f"MINING#{now_iso()}",
            "METADATA",
            {"source": source, "imported": imported, "hot": len(hot_leads)},
        )
        return {"imported": imported, "hot_leads": len(hot_leads), "queued_calls": 0}

    async def process_mined_leads(self, limit: int = 20) -> dict[str, Any]:
        leads = await lead_repo.get_hot_leads(limit=limit)
        called = 0
        skipped = 0

        for lead in leads:
            if lead.get("status") not in {"new", "contacted", "qualified"}:
                skipped += 1
                continue
            on_dnc = await lead_repo.is_on_dnc(lead["phone"])
            if on_dnc:
                skipped += 1
                continue
            result = await initiate_outbound_call(
                lead["phone"],
                {
                    "lead_id": lead["id"],
                    "opt_in_voice": lead.get("opt_in_voice", True),
                    "on_dnc": on_dnc,
                    "origin": lead.get("origin"),
                    "destination": lead.get("destination"),
                    "departure_date": lead.get("departure_date"),
                    "passengers": lead.get("passengers", 1),
                    "market": lead.get("market", "uae"),
                    "preferred_language": lead.get("preferred_language", "en"),
                    "temperature": lead.get("temperature", "hot"),
                },
            )
            if result.get("success"):
                await lead_repo.update_status(lead["id"], "contacted")
                called += 1

        return {"processed": len(leads), "called": called, "skipped": skipped}

    async def import_batch(self, leads: list[dict[str, Any]], source: str = "manual") -> dict[str, Any]:
        return await self.ingest_webhook({"leads": leads}, source=source)

    def _normalize(self, raw: dict[str, Any], source: str) -> dict[str, Any]:
        phone = raw.get("phone") or raw.get("mobile") or raw.get("Phone")
        return {
            "phone": str(phone).strip() if phone else "",
            "email": raw.get("email") or raw.get("Email"),
            "name": raw.get("name") or raw.get("full_name") or raw.get("Name"),
            "employer": raw.get("company") or raw.get("employer") or raw.get("Organization"),
            "location": raw.get("location") or raw.get("city") or raw.get("Country"),
            "origin": raw.get("origin") or raw.get("home_airport"),
            "destination": raw.get("destination"),
            "departure_date": raw.get("departure_date"),
            "market": raw.get("market", "uae"),
            "source": source,
            "opt_in_voice": raw.get("opt_in_voice", False),
            "opt_in_marketing": raw.get("opt_in_marketing", True),
            "source_detail": raw.get("source_detail") or source,
        }


lead_mining = LeadMiningService()
