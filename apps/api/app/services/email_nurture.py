"""Abandoned search recovery and nurture email sequences."""

import logging
import smtplib
from email.mime.text import MIMEText
from typing import Any

from app.config import get_settings
from app.storage.dynamo import events_store, leads_store, now_iso

logger = logging.getLogger("travel-ai-nurture")
settings = get_settings()


async def send_abandoned_search_emails() -> dict[str, Any]:
    store = events_store()
    if not store.enabled:
        return {"sent": 0, "reason": "local mode"}

    abandoned = store.query_gsi1("ABANDONED_SEARCH", limit=20)
    sent = 0

    for event in abandoned:
        if event.get("nurture_sent"):
            continue
        email = event.get("email")
        if not email:
            continue

        origin = event.get("origin", "")
        destination = event.get("destination", "")
        subject = f"Still planning {origin} → {destination}? We found new deals ✈️"
        body = (
            f"Hi there,\n\n"
            f"You were searching for flights from {origin} to {destination}. "
            f"Prices change fast — reply to this email or chat with Sarah at {settings.site_url} "
            f"to lock in today's best fare.\n\n"
            f"— Sarah, TravelAI\n"
        )

        if _send_email(email, subject, body):
            store.update(event["PK"], event["SK"], {"nurture_sent": True, "nurture_sent_at": now_iso()})
            sent += 1

    return {"sent": sent, "checked": len(abandoned)}


def track_abandoned_search(
    email: str,
    origin: str,
    destination: str,
    departure_date: str = "",
) -> None:
    store = events_store()
    if not store.enabled:
        return
    ts = now_iso()
    store.put(
        "ABANDONED_SEARCH",
        f"{email}#{ts}",
        {
            "email": email,
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "nurture_sent": False,
        },
        gsi1pk="ABANDONED_SEARCH",
        gsi1sk=ts,
    )


def _send_email(to: str, subject: str, body: str) -> bool:
    if not settings.smtp_pass or not settings.smtp_user:
        logger.info("Mock email to %s: %s", to, subject)
        return True

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from
        msg["To"] = to

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            if settings.smtp_port == 587:
                server.starttls()
            server.login(settings.smtp_user, settings.smtp_pass)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False
