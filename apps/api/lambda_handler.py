"""AWS Lambda entrypoint for FastAPI via Mangum."""

import os

from mangum import Mangum

from app.main import app

_stage = os.environ.get("API_GATEWAY_STAGE", "")
_base = f"/{_stage}" if _stage else None

handler = Mangum(app, lifespan="auto", api_gateway_base_path=_base)

