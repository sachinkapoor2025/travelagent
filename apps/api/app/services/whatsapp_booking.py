"""Post-call WhatsApp booking completion flow."""

from typing import Any, Optional

from app.services.payments import create_payment_link
from app.services.whatsapp import whatsapp_service
from app.storage.bookings_repo import booking_repo


class WhatsAppBookingService:
    async def send_post_call_quote(
        self,
        phone: str,
        session: dict[str, Any],
        transcript: Optional[str] = None,
    ) -> dict[str, Any]:
        origin = session.get("origin", "DXB")
        destination = session.get("destination", "BOM")
        offers = session.get("last_search") or []
        booking = session.get("booking")

        if booking:
            return await self._send_payment_flow(phone, booking, session)

        if offers:
            best = offers[0]
            price = best.get("price", 0)
            currency = best.get("currency", "AED")
            summary = best.get("summary") or f"{origin}→{destination}"
            message = (
                f"Hi! Sarah from TravelAI here 👋\n\n"
                f"Thanks for your call. Best fare I found:\n"
                f"✈ {summary}\n"
                f"💰 {currency} {price:,.0f}\n\n"
                f"Reply BOOK to confirm or SEARCH for more options."
            )
            await whatsapp_service.send_text(phone, message)
            return {"status": "quote_sent", "offer": best}

        message = (
            f"Hi from TravelAI! Thanks for speaking with Sarah.\n"
            f"Tell me your route (e.g. DXB to MEL) and I'll send live prices within 2 minutes."
        )
        await whatsapp_service.send_text(phone, message)
        return {"status": "follow_up_sent"}

    async def _send_payment_flow(self, phone: str, booking: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
        booking_id = booking.get("booking_id") or booking.get("id")
        record = await booking_repo.get(str(booking_id))
        if not record:
            return {"status": "booking_not_found"}

        payment = await create_payment_link(record, session.get("market", "uae"), phone)
        link = payment.get("payment_link_url", "")
        amount = record.get("total_amount", 0)
        currency = record.get("currency", "AED")

        message = (
            f"Your booking is ready! 🎫\n"
            f"Ref: {record.get('pnr') or booking_id}\n"
            f"Amount: {currency} {amount:,.0f}\n\n"
            f"Pay securely: {link}\n\n"
            f"Visa · Mastercard · Amex · RuPay · UPI accepted."
        )
        await whatsapp_service.send_text(phone, message)
        return {"status": "payment_link_sent", "payment_link": link}

    async def handle_booking_reply(self, phone: str, text: str, session: dict[str, Any]) -> dict[str, Any]:
        normalized = text.strip().upper()
        if normalized == "BOOK":
            offers = session.get("last_search") or []
            if not offers:
                return {"status": "no_offers", "message": "Search for flights first"}
            from app.services.travel_tools import execute_tool

            result = await execute_tool(
                session.get("session_id", phone),
                "create_booking",
                {"offer_id": offers[0]["offer_id"], "passengers": [{"type": "adult"}]},
                session,
            )
            if result.get("booking_id"):
                return await self._send_payment_flow(phone, result, session)
            return result
        return {"status": "ignored"}


whatsapp_booking = WhatsAppBookingService()
