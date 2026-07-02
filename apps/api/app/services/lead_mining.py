"""Internet lead mining — Clay/Apollo webhooks, automated sources, and batch import."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.lead_enrichment import lead_enrichment
from app.services.lead_segment import classify_segment
from app.services.miners.auto_action import auto_action_lead
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
        actions: dict[str, int] = {}

        for raw in leads_raw:
            lead_data = self._normalize(raw, source)
            lead_data["lead_segment"] = classify_segment(source, lead_data.get("lead_segment"))
            if not lead_data.get("phone") and not lead_data.get("destination"):
                continue
            saved = await self._save_lead(await lead_enrichment.enrich(lead_data))
            imported += 1
            action = await auto_action_lead(saved)
            actions[action] = actions.get(action, 0) + 1

        events_store().put(
            f"MINING#{now_iso()}",
            "METADATA",
            {"source": source, "imported": imported, "actions": actions},
        )
        return {"imported": imported, "actions": actions}

    async def _save_lead(self, enriched: dict[str, Any]) -> dict[str, Any]:
        return await lead_repo.create_or_update(enriched)

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

    async def dashboard(self) -> dict[str, Any]:
        from app.services.mining_config import get_sources
        from app.services.source_labels import enrich_lead_display, source_display_label

        leads = await lead_repo.list_leads(limit=200)
        today = datetime.now(timezone.utc).date().isoformat()
        today_leads = [l for l in leads if (l.get("created_at") or "").startswith(today)]

        by_source: dict[str, int] = {}
        pipeline = []
        for lead in sorted(leads, key=lambda x: x.get("created_at", ""), reverse=True)[:200]:
            display = enrich_lead_display(lead)
            src = lead.get("source", "unknown")
            by_source[src] = by_source.get(src, 0) + 1
            pipeline.append(
                {
                    "id": display.get("id"),
                    "phone": display.get("phone"),
                    "name": display.get("name"),
                    "location": display.get("location"),
                    "route": display.get("route") or f"{display.get('origin') or '—'} → {display.get('destination') or '—'}",
                    "origin": display.get("origin"),
                    "destination": display.get("destination"),
                    "departure_date": display.get("departure_date"),
                    "return_date": display.get("return_date"),
                    "budget_max": display.get("budget_max"),
                    "passengers": display.get("passengers"),
                    "score": display.get("score"),
                    "temperature": display.get("temperature"),
                    "language": display.get("preferred_language"),
                    "source": src,
                    "source_label": display.get("source_label") or source_display_label(src, display.get("source_detail")),
                    "source_detail": display.get("source_detail"),
                    "travel_intent": display.get("travel_intent"),
                    "market": display.get("market"),
                    "lead_segment": display.get("lead_segment"),
                    "segment_label": display.get("segment_label"),
                    "contact_synthetic": display.get("contact_synthetic"),
                    "call_ready": display.get("call_ready"),
                    "status": display.get("status"),
                    "notes": display.get("notes"),
                    "created_at": display.get("created_at"),
                }
            )

        sources = get_sources()
        source_stats = []
        for sid, cfg in sources.items():
            source_stats.append(
                {
                    "id": sid,
                    "label": cfg.get("label", sid),
                    "enabled": cfg.get("enabled", False),
                    "schedule": cfg.get("schedule", ""),
                    "today_count": sum(1 for l in today_leads if l.get("source") == sid),
                }
            )

        return {
            "sources": source_stats,
            "today_total": len(today_leads),
            "today_by_source": {s["id"]: s["today_count"] for s in source_stats},
            "pipeline": pipeline,
            "total_mined": len(leads),
        }

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
            "travel_intent": raw.get("travel_intent"),
            "lead_segment": raw.get("lead_segment") or classify_segment(source),
            "notes": raw.get("notes") or raw.get("context") or raw.get("snippet"),
        }


lead_mining = LeadMiningService()
