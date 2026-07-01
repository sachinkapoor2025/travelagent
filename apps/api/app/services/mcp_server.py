"""MCP-style tools exposing TravelAI inventory to external AI agents."""

from typing import Any

from app.models import Market
from app.schemas import FlightSearchRequest, HotelSearchRequest
from app.services.agentic_booking import agentic_booking
from app.services.booking import duffel_client
from app.services.hotels import hotel_service
from app.services.price_predictor import price_predictor


MCP_TOOLS = [
    {
        "name": "search_flights",
        "description": "Search live flight offers for a route",
        "inputSchema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "IATA origin code"},
                "destination": {"type": "string", "description": "IATA destination code"},
                "departure_date": {"type": "string", "format": "date"},
                "passengers": {"type": "integer", "default": 1},
            },
            "required": ["origin", "destination", "departure_date"],
        },
    },
    {
        "name": "search_hotels",
        "description": "Search hotels in a city",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "check_in": {"type": "string"},
                "check_out": {"type": "string"},
                "guests": {"type": "integer", "default": 2},
            },
            "required": ["city", "check_in", "check_out"],
        },
    },
    {
        "name": "price_predict",
        "description": "Get buy-now-or-wait recommendation for a route",
        "inputSchema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string"},
                "destination": {"type": "string"},
                "departure_date": {"type": "string"},
                "market": {"type": "string", "enum": ["uae", "india"]},
            },
            "required": ["origin", "destination", "departure_date"],
        },
    },
    {
        "name": "agentic_book",
        "description": "Autonomously search, book, and send payment link",
        "inputSchema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string"},
                "destination": {"type": "string"},
                "departure_date": {"type": "string"},
                "phone": {"type": "string"},
                "passengers": {"type": "integer", "default": 1},
            },
            "required": ["origin", "destination", "departure_date", "phone"],
        },
    },
]


class MCPServerService:
    def list_tools(self) -> dict[str, Any]:
        return {"tools": MCP_TOOLS, "protocol": "mcp-compatible", "version": "1.0"}

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "search_flights":
            req = FlightSearchRequest(
                origin=arguments["origin"].upper(),
                destination=arguments["destination"].upper(),
                departure_date=arguments["departure_date"],
                passengers=arguments.get("passengers", 1),
                market=Market(arguments.get("market", "uae")),
            )
            results = await duffel_client.search_flights(req)
            return {"offers": [o.model_dump() for o in results.offers[:5]]}

        if name == "search_hotels":
            req = HotelSearchRequest(
                city=arguments["city"],
                check_in=arguments["check_in"],
                check_out=arguments["check_out"],
                guests=arguments.get("guests", 2),
                market=Market(arguments.get("market", "uae")),
            )
            hotels = await hotel_service.search_hotels(req)
            return {"hotels": [h.model_dump() for h in hotels[:5]]}

        if name == "price_predict":
            return await price_predictor.predict(
                arguments["origin"],
                arguments["destination"],
                arguments["departure_date"],
                Market(arguments.get("market", "uae")),
            )

        if name == "agentic_book":
            session_id = await agentic_booking.create_session(
                phone=arguments.get("phone"),
                market=Market(arguments.get("market", "uae")),
            )
            return await agentic_booking.run_booking_loop(
                session_id,
                arguments["origin"].upper(),
                arguments["destination"].upper(),
                arguments["departure_date"],
                arguments.get("passengers", 1),
                phone=arguments.get("phone"),
                market=Market(arguments.get("market", "uae")),
            )

        return {"error": f"Unknown tool: {name}"}


mcp_server = MCPServerService()
