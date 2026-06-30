#!/usr/bin/env python3
"""Register Vapi assistant with TravelAI tool webhooks."""

import json
import os
import sys

import httpx

VAPI_API_KEY = os.environ.get("VAPI_API_KEY", "")
SERVER_URL = os.environ.get("SERVER_URL", "https://your-domain.com")


def main() -> None:
    if not VAPI_API_KEY:
        print("Set VAPI_API_KEY environment variable")
        sys.exit(1)

    from app.services.voice import get_vapi_assistant_config

    config = get_vapi_assistant_config(SERVER_URL)

    response = httpx.post(
        "https://api.vapi.ai/assistant",
        headers={"Authorization": f"Bearer {VAPI_API_KEY}", "Content-Type": "application/json"},
        json=config,
        timeout=30.0,
    )
    response.raise_for_status()
    assistant = response.json()
    print("Assistant created:")
    print(json.dumps({"id": assistant.get("id"), "name": assistant.get("name")}, indent=2))
    print("\nSet VAPI_ASSISTANT_ID=" + assistant.get("id", ""))


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
    main()
