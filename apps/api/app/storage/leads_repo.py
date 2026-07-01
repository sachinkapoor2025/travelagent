"""Lead + DNC repository — DynamoDB only."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from app.config import get_settings
from app.models import LeadSource, LeadStatus, Market
from app.services.leads import calculate_lead_score
from app.storage.dynamo import leads_store, now_iso

settings = get_settings()


def _dict_to_lead(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": data.get("id", data.get("lead_id")),
        "phone": data["phone"],
        "email": data.get("email"),
        "name": data.get("name"),
        "market": data.get("market", "uae"),
        "source": data.get("source", "website"),
        "status": data.get("status", "new"),
        "score": int(data.get("score", 0)),
        "preferred_language": data.get("preferred_language"),
        "origin": data.get("origin"),
        "destination": data.get("destination"),
        "departure_date": data.get("departure_date"),
        "return_date": data.get("return_date"),
        "passengers": int(data.get("passengers", 1)),
        "cabin_class": data.get("cabin_class"),
        "budget_max": data.get("budget_max"),
        "stop_preference": data.get("stop_preference"),
        "opt_in_marketing": data.get("opt_in_marketing", False),
        "opt_in_voice": data.get("opt_in_voice", False),
        "created_at": data.get("created_at", now_iso()),
    }


class LeadRepository:
    async def create_or_update(self, data: dict[str, Any]) -> dict[str, Any]:
        store = leads_store()
        phone = data["phone"]
        existing = store.query_gsi1(f"PHONE#{phone}", limit=1)
        lead_id = existing[0].get("id") if existing else str(uuid.uuid4())
        ts = now_iso()

        record = {
            "id": lead_id,
            "lead_id": lead_id,
            "phone": phone,
            "email": data.get("email"),
            "name": data.get("name"),
            "market": data.get("market", "uae"),
            "source": data.get("source", "website"),
            "status": data.get("status", "new"),
            "origin": data.get("origin"),
            "destination": data.get("destination"),
            "departure_date": data.get("departure_date"),
            "return_date": data.get("return_date"),
            "passengers": data.get("passengers", 1),
            "cabin_class": data.get("cabin_class"),
            "budget_max": data.get("budget_max"),
            "stop_preference": data.get("stop_preference"),
            "opt_in_marketing": data.get("opt_in_marketing", False),
            "opt_in_voice": data.get("opt_in_voice", False),
            "updated_at": ts,
        }
        if not existing:
            record["created_at"] = ts

        record["score"] = _score_from_dict(record)
        if record["score"] >= settings.lead_hot_score_threshold:
            record["status"] = LeadStatus.QUALIFIED.value

        store.put(f"LEAD#{lead_id}", "METADATA", record, gsi1pk="LEADS", gsi1sk=f"{record['score']:03d}#{ts}")
        store.put(f"LEAD#{lead_id}", "METADATA", record, gsi1pk=f"PHONE#{phone}", gsi1sk=lead_id)
        return _dict_to_lead(record)

    async def list_leads(self, status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        items = leads_store().query_gsi1("LEADS", limit=limit)
        leads = [_dict_to_lead(i) for i in items]
        if status:
            leads = [l for l in leads if l["status"] == status]
        return leads

    async def get_by_id(self, lead_id: str) -> Optional[dict[str, Any]]:
        item = leads_store().get(f"LEAD#{lead_id}", "METADATA")
        return _dict_to_lead(item) if item else None

    async def get_hot_leads(self, limit: int = 10) -> list[dict[str, Any]]:
        leads = await self.list_leads(limit=100)
        hot = [l for l in leads if l["score"] >= settings.lead_warm_score_threshold]
        hot.sort(key=lambda x: x["score"], reverse=True)
        return hot[:limit]

    async def update_status(self, lead_id: str, status: str) -> None:
        leads_store().update(f"LEAD#{lead_id}", "METADATA", {"status": status, "updated_at": now_iso()})

    async def is_on_dnc(self, phone: str) -> bool:
        return leads_store().get(f"DNC#{phone}", "METADATA") is not None

    async def add_to_dnc(self, phone: str, market: str, reason: str = "Customer request") -> None:
        leads_store().put(
            f"DNC#{phone}",
            "METADATA",
            {"phone": phone, "market": market, "reason": reason, "created_at": now_iso()},
        )


def _score_from_dict(data: dict[str, Any]) -> int:
    class FakeLead:
        pass

    lead = FakeLead()
    for k, v in data.items():
        setattr(lead, k, v)
    lead.market = Market(data.get("market", "uae"))
    lead.source = LeadSource(data.get("source", "website"))
    lead.opt_in_voice = data.get("opt_in_voice", False)
    lead.passengers = int(data.get("passengers", 1))
    return calculate_lead_score(lead)  # type: ignore[arg-type]


lead_repo = LeadRepository()
