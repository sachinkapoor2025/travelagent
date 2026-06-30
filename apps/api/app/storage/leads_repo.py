"""Lead repository — Postgres locally, DynamoDB on AWS SAM."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Lead, LeadSource, LeadStatus, Market
from app.services.leads import calculate_lead_score, classify_lead
from app.storage.dynamo import leads_store, now_iso

settings = get_settings()


def _lead_to_dict(lead: Lead) -> dict[str, Any]:
    return {
        "id": str(lead.id),
        "phone": lead.phone,
        "email": lead.email,
        "name": lead.name,
        "market": lead.market.value if lead.market else "uae",
        "source": lead.source.value if lead.source else "website",
        "status": lead.status.value if lead.status else "new",
        "score": lead.score,
        "preferred_language": lead.preferred_language.value if lead.preferred_language else None,
        "origin": lead.origin,
        "destination": lead.destination,
        "departure_date": lead.departure_date,
        "return_date": lead.return_date,
        "passengers": lead.passengers,
        "cabin_class": lead.cabin_class,
        "budget_max": lead.budget_max,
        "stop_preference": lead.stop_preference,
        "opt_in_marketing": lead.opt_in_marketing,
        "opt_in_voice": lead.opt_in_voice,
        "created_at": lead.created_at.isoformat() if lead.created_at else now_iso(),
    }


def _dict_to_lead_response(data: dict[str, Any]) -> dict[str, Any]:
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
        "created_at": data.get("created_at", now_iso()),
    }


class LeadRepository:
    async def create_or_update(self, db: Optional[AsyncSession], data: dict[str, Any]) -> dict[str, Any]:
        if settings.use_dynamo:
            return self._create_or_update_dynamo(data)
        assert db
        lead = await self._create_or_update_sql(db, data)
        return _lead_to_dict(lead)

    async def list_leads(self, db: Optional[AsyncSession], limit: int = 50) -> list[dict[str, Any]]:
        if settings.use_dynamo:
            store = leads_store()
            items = store.query_gsi1("LEADS", limit=limit)
            return [_dict_to_lead_response(i) for i in items]
        assert db
        result = await db.execute(select(Lead).order_by(Lead.score.desc()).limit(limit))
        return [_lead_to_dict(l) for l in result.scalars().all()]

    async def get_by_id(self, db: Optional[AsyncSession], lead_id: str) -> Optional[dict[str, Any]]:
        if settings.use_dynamo:
            item = leads_store().get(f"LEAD#{lead_id}", "METADATA")
            return _dict_to_lead_response(item) if item else None
        assert db
        lead = await db.get(Lead, uuid.UUID(lead_id))
        return _lead_to_dict(lead) if lead else None

    async def get_hot_leads(self, db: Optional[AsyncSession], limit: int = 10) -> list[dict[str, Any]]:
        leads = await self.list_leads(db, limit=100)
        hot = [l for l in leads if l["score"] >= settings.lead_warm_score_threshold]
        hot.sort(key=lambda x: x["score"], reverse=True)
        return hot[:limit]

    async def update_status(self, db: Optional[AsyncSession], lead_id: str, status: str) -> None:
        if settings.use_dynamo:
            leads_store().update(f"LEAD#{lead_id}", "METADATA", {"status": status, "updated_at": now_iso()})
            return
        assert db
        lead = await db.get(Lead, uuid.UUID(lead_id))
        if lead:
            lead.status = LeadStatus(status)

    def _create_or_update_dynamo(self, data: dict[str, Any]) -> dict[str, Any]:
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

        score = self._score_from_dict(record)
        record["score"] = score
        if score >= settings.lead_hot_score_threshold:
            record["status"] = "qualified"

        store.put(f"LEAD#{lead_id}", "METADATA", record, gsi1pk="LEADS", gsi1sk=f"{score:03d}#{ts}")
        store.put(f"LEAD#{lead_id}", "METADATA", record, gsi1pk=f"PHONE#{phone}", gsi1sk=lead_id)
        return _dict_to_lead_response(record)

    async def _create_or_update_sql(self, db: AsyncSession, data: dict[str, Any]) -> Lead:
        from app.services.leads import create_or_update_lead

        return await create_or_update_lead(db, data)

    def _score_from_dict(self, data: dict[str, Any]) -> int:
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
