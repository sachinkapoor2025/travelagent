"""Meta & Google lead form webhook ingestion."""

from typing import Any

from app.models import LeadSource
from app.services.compliance import detect_market_from_phone
from app.storage.leads_repo import lead_repo


async def ingest_meta_lead(payload: dict[str, Any]) -> dict[str, Any]:
    """Process Meta Lead Ads webhook payload."""
    entry = payload.get("entry", [{}])[0]
    changes = entry.get("changes", [{}])[0]
    value = changes.get("value", {})
    field_data = {f["name"]: f["values"][0] for f in value.get("field_data", []) if f.get("values")}

    phone = field_data.get("phone_number", field_data.get("phone", ""))
    if not phone.startswith("+"):
        phone = f"+{phone}"

    data = {
        "phone": phone,
        "email": field_data.get("email"),
        "name": field_data.get("full_name", field_data.get("first_name", "")),
        "origin": field_data.get("origin", field_data.get("from", "")),
        "destination": field_data.get("destination", field_data.get("to", "")),
        "departure_date": field_data.get("travel_date", field_data.get("departure_date")),
        "source": LeadSource.META_ADS.value,
        "market": detect_market_from_phone(phone).value,
        "opt_in_voice": True,
        "opt_in_marketing": True,
    }

    lead = await lead_repo.create_or_update(None, data)
    return {"status": "created", "lead": lead}


async def ingest_google_lead(payload: dict[str, Any]) -> dict[str, Any]:
    """Process Google Ads lead form extension webhook."""
    user = payload.get("user_column_data", [])
    fields = {item["column_id"]: item.get("string_value", "") for item in user}

    phone = fields.get("PHONE_NUMBER", fields.get("phone", ""))
    if phone and not phone.startswith("+"):
        phone = f"+{phone}"

    data = {
        "phone": phone,
        "email": fields.get("EMAIL", fields.get("email")),
        "name": fields.get("FULL_NAME", fields.get("name", "")),
        "origin": fields.get("origin", ""),
        "destination": fields.get("destination", ""),
        "source": LeadSource.GOOGLE_ADS.value,
        "market": detect_market_from_phone(phone).value if phone else "uae",
        "opt_in_voice": True,
        "opt_in_marketing": True,
    }

    lead = await lead_repo.create_or_update(None, data)
    return {"status": "created", "lead": lead}
