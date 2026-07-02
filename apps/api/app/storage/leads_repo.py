"""Lead + DNC repository — DynamoDB only."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from app.config import get_settings
from app.models import LeadSource, LeadStatus, Market
from app.services.leads import calculate_lead_score
from app.services.lead_segment import classify_segment, segment_display
from app.services.source_labels import enrich_lead_display
from app.storage.dynamo import leads_store, now_iso

settings = get_settings()

_EXTRA_FIELDS = (
    "location",
    "source_detail",
    "travel_intent",
    "enrichment",
    "notes",
    "temperature",
    "preferred_language",
    "lead_segment",
    "lead_category",
    "contact_synthetic",
    "call_ready",
    "external_id",
    "post_url",
    "contact_url",
    "scored",
    "scorer_action",
    "scorer_reason",
    "call_opener",
    "whatsapp_message",
    "message_at",
)


def _dict_to_lead(data: dict[str, Any]) -> dict[str, Any]:
    lead = {
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
    for field in _EXTRA_FIELDS:
        if data.get(field) is not None:
            lead[field] = data[field]
    if not lead.get("lead_segment"):
        lead["lead_segment"] = classify_segment(lead.get("source"))
    lead["segment_label"] = segment_display(lead.get("lead_segment"))
    return enrich_lead_display(lead)


def _market_filter_active(market: Optional[str]) -> bool:
    if not market:
        return False
    return market.strip().lower() not in {"", "worldwide", "all", "any", "global"}


def _matches_query(lead: dict[str, Any], q: str) -> bool:
    needle = q.lower().strip()
    if not needle:
        return True
    haystacks = [
        lead.get("phone"),
        lead.get("name"),
        lead.get("email"),
        lead.get("origin"),
        lead.get("destination"),
        lead.get("location"),
        lead.get("market"),
        lead.get("source"),
        lead.get("source_label"),
        lead.get("source_detail"),
        lead.get("travel_intent"),
        lead.get("notes"),
        lead.get("status"),
        lead.get("lead_segment"),
        lead.get("segment_label"),
    ]
    enrichment = lead.get("enrichment") or {}
    if isinstance(enrichment, dict):
        haystacks.extend(str(v) for v in enrichment.values() if v)
    return any(needle in str(value).lower() for value in haystacks if value)


class LeadRepository:
    async def create_or_update(self, data: dict[str, Any]) -> dict[str, Any]:
        store = leads_store()
        phone = data["phone"]
        existing = store.query_gsi1(f"PHONE#{phone}", limit=1)
        if existing:
            lead_id = existing[0].get("lead_id") or existing[0].get("id") or str(uuid.uuid4())
        else:
            lead_id = str(uuid.uuid4())
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
        for field in _EXTRA_FIELDS:
            if data.get(field) is not None:
                record[field] = data[field]
        if not existing:
            record["created_at"] = ts

        record["score"] = data.get("score") if data.get("score") is not None else _score_from_dict(record)
        if data.get("temperature"):
            record["temperature"] = data["temperature"]
        elif record["score"] >= settings.lead_hot_score_threshold:
            record["temperature"] = "hot"
        elif record["score"] >= settings.lead_warm_score_threshold:
            record["temperature"] = "warm"
        else:
            record["temperature"] = "cold"
        if record["score"] >= settings.lead_hot_score_threshold:
            record["status"] = LeadStatus.QUALIFIED.value

        store.put(f"LEAD#{lead_id}", "METADATA", record, gsi1pk="LEADS", gsi1sk=f"{record['score']:03d}#{ts}")
        store.put(
            f"PHONE#{phone}",
            f"LEAD#{lead_id}",
            {"lead_id": lead_id, "phone": phone},
            gsi1pk=f"PHONE#{phone}",
            gsi1sk=lead_id,
        )
        return _dict_to_lead(record)

    async def list_leads(
        self,
        status: Optional[str] = None,
        market: Optional[str] = None,
        source: Optional[str] = None,
        segment: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        items = leads_store().query_gsi1("LEADS", limit=max(limit, 300))
        leads = [_dict_to_lead(i) for i in items]
        if status:
            leads = [l for l in leads if l["status"] == status]
        if market and _market_filter_active(market):
            needle = market.lower()
            leads = [l for l in leads if needle in str(l.get("market", "")).lower() or needle in str(l.get("location", "")).lower()]
        if source:
            leads = [l for l in leads if l.get("source") == source]
        if segment:
            leads = [l for l in leads if l.get("lead_segment") == segment]
            if segment == "b2c":
                leads = [
                    l for l in leads
                    if l.get("lead_category") not in {"deal_channel", "discarded", "b2b"}
                ]
        if q:
            leads = [l for l in leads if _matches_query(l, q)]
        leads.sort(
            key=lambda x: (
                0 if x.get("lead_segment") == "b2c" and x.get("lead_category") not in {"deal_channel", "discarded", "b2b"} else 1,
                -(x.get("score") or 0),
                x.get("created_at", ""),
            ),
        )
        return leads[:limit]

    async def list_unscored_leads(self, limit: int = 30) -> list[dict[str, Any]]:
        items = leads_store().query_gsi1("LEADS", limit=max(limit * 4, 200))
        leads = [_dict_to_lead(i) for i in items]
        unscored = [
            l for l in leads
            if l.get("scored") is False and l.get("lead_category") not in {"deal_channel", "discarded", "b2b"}
        ]
        unscored.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return unscored[:limit]

    async def update_lead_fields(self, lead_id: str, fields: dict[str, Any]) -> None:
        store = leads_store()
        existing = store.get(f"LEAD#{lead_id}", "METADATA")
        if not existing:
            return
        record = dict(existing)
        record.update(fields)
        record["updated_at"] = now_iso()
        score = int(record.get("score", 0))
        ts = record.get("created_at") or now_iso()
        store.put(
            f"LEAD#{lead_id}",
            "METADATA",
            record,
            gsi1pk="LEADS",
            gsi1sk=f"{score:03d}#{ts}",
        )

    async def get_by_id(self, lead_id: str) -> Optional[dict[str, Any]]:
        item = leads_store().get(f"LEAD#{lead_id}", "METADATA")
        return _dict_to_lead(item) if item else None

    async def list_by_phone(self, phone: str) -> list[dict[str, Any]]:
        items = leads_store().query_gsi1(f"PHONE#{phone}", limit=5)
        leads: list[dict[str, Any]] = []
        for item in items:
            lead_id = item.get("lead_id") or item.get("id")
            if not lead_id:
                continue
            lead = await self.get_by_id(str(lead_id))
            if lead:
                leads.append(lead)
        return leads

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
    try:
        lead.market = Market(data.get("market", "uae"))
    except ValueError:
        lead.market = Market.UAE
    try:
        lead.source = LeadSource(data.get("source", "website"))
    except ValueError:
        lead.source = LeadSource.WEBSITE
    lead.opt_in_voice = data.get("opt_in_voice", False)
    lead.passengers = int(data.get("passengers", 1))
    return calculate_lead_score(lead)  # type: ignore[arg-type]


lead_repo = LeadRepository()
