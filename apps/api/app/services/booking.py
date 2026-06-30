"""Duffel flight search and booking integration."""

from typing import Any

import httpx

from app.config import get_settings
from app.schemas import FlightOffer, FlightSearchRequest, FlightSearchResponse

settings = get_settings()


class DuffelClient:
    def __init__(self) -> None:
        self.base_url = settings.duffel_base_url
        self.token = settings.duffel_api_token

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Duffel-Version": "v2",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def search_flights(self, request: FlightSearchRequest) -> FlightSearchResponse:
        if not self.token:
            return self._mock_search(request)

        slices = [{"origin": request.origin, "destination": request.destination, "departure_date": request.departure_date}]
        if request.return_date:
            slices.append(
                {"origin": request.destination, "destination": request.origin, "departure_date": request.return_date}
            )

        payload = {
            "data": {
                "slices": slices,
                "passengers": [{"type": "adult"} for _ in range(request.passengers)],
                "cabin_class": request.cabin_class,
            }
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self.base_url}/air/offer_requests", headers=self.headers, json=payload)
            response.raise_for_status()
            offer_request = response.json()["data"]

            offers_resp = await client.get(
                f"{self.base_url}/air/offers",
                headers=self.headers,
                params={"offer_request_id": offer_request["id"], "limit": 10},
            )
            offers_resp.raise_for_status()
            offers_data = offers_resp.json()["data"]

        offers = [self._parse_offer(o) for o in offers_data]
        if request.max_stops is not None:
            offers = [o for o in offers if o.stops <= request.max_stops]

        return FlightSearchResponse(offers=offers[:5], search_id=offer_request["id"])

    async def create_order(self, offer_id: str, passengers: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.token:
            return {
                "id": f"mock_order_{offer_id[:8]}",
                "booking_reference": "MOCKPNR1",
                "total_amount": "1299.00",
                "total_currency": "AED",
            }

        payload = {
            "data": {
                "selected_offers": [offer_id],
                "passengers": passengers,
                "payments": [{"type": "balance", "currency": "AED", "amount": "0"}],
            }
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{self.base_url}/air/orders", headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()["data"]

    def _parse_offer(self, offer: dict[str, Any]) -> FlightOffer:
        slice_data = offer["slices"][0]
        segment = slice_data["segments"][0]
        stops = max(len(slice_data["segments"]) - 1, 0)
        airline = segment["operating_carrier"]["name"]
        flight_number = f"{segment['operating_carrier']['iata_code']}{segment['operating_carrier_flight_number']}"

        return FlightOffer(
            offer_id=offer["id"],
            airline=airline,
            flight_number=flight_number,
            origin=slice_data["origin"]["iata_code"],
            destination=slice_data["destination"]["iata_code"],
            departure_at=segment["departing_at"],
            arrival_at=segment["arriving_at"],
            duration=slice_data.get("duration", "N/A"),
            stops=stops,
            price=float(offer["total_amount"]),
            currency=offer["total_currency"],
            cabin_class=offer.get("cabin_class", "economy"),
            summary=(
                f"{airline} {flight_number}: {slice_data['origin']['iata_code']} to "
                f"{slice_data['destination']['iata_code']}, {stops} stop(s), "
                f"{offer['total_currency']} {offer['total_amount']}"
            ),
        )

    def _mock_search(self, request: FlightSearchRequest) -> FlightSearchResponse:
        currency = "AED" if request.market.value == "uae" else "INR"
        base_price = 1299.0 if currency == "AED" else 45999.0
        offers = [
            FlightOffer(
                offer_id=f"mock_offer_direct_{request.origin}_{request.destination}",
                airline="Emirates" if request.market.value == "uae" else "IndiGo",
                flight_number="EK501" if request.market.value == "uae" else "6E1402",
                origin=request.origin.upper(),
                destination=request.destination.upper(),
                departure_at=f"{request.departure_date}T08:30:00",
                arrival_at=f"{request.departure_date}T14:45:00",
                duration="PT6H15M",
                stops=0,
                price=base_price,
                currency=currency,
                cabin_class=request.cabin_class,
                summary=(
                    f"Direct flight {request.origin.upper()} to {request.destination.upper()} — "
                    f"{currency} {base_price:.0f}"
                ),
            ),
            FlightOffer(
                offer_id=f"mock_offer_1stop_{request.origin}_{request.destination}",
                airline="Qatar Airways",
                flight_number="QR815",
                origin=request.origin.upper(),
                destination=request.destination.upper(),
                departure_at=f"{request.departure_date}T11:00:00",
                arrival_at=f"{request.departure_date}T22:30:00",
                duration="PT11H30M",
                stops=1,
                price=base_price * 0.82,
                currency=currency,
                cabin_class=request.cabin_class,
                summary=(
                    f"1-stop via DOH {request.origin.upper()} to {request.destination.upper()} — "
                    f"{currency} {base_price * 0.82:.0f}"
                ),
            ),
            FlightOffer(
                offer_id=f"mock_offer_2stop_{request.origin}_{request.destination}",
                airline="Air India",
                flight_number="AI919",
                origin=request.origin.upper(),
                destination=request.destination.upper(),
                departure_at=f"{request.departure_date}T06:15:00",
                arrival_at=f"{request.departure_date}T19:40:00",
                duration="PT13H25M",
                stops=2,
                price=base_price * 0.68,
                currency=currency,
                cabin_class=request.cabin_class,
                summary=(
                    f"2-stop budget option {request.origin.upper()} to {request.destination.upper()} — "
                    f"{currency} {base_price * 0.68:.0f}"
                ),
            ),
        ]
        if request.max_stops is not None:
            offers = [o for o in offers if o.stops <= request.max_stops]
        return FlightSearchResponse(offers=offers, search_id="mock_search_id")


duffel_client = DuffelClient()
