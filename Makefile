.PHONY: dev install migrate docker-up docker-down test sam-build sam-deploy setup-vapi

install:
	cd apps/api && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

dev:
	cd apps/api && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	cd apps/api && .venv/bin/python -m app.worker

docker-up:
	docker compose up --build

docker-down:
	docker compose down

test:
	cd apps/api && .venv/bin/python -c "from app.main import app; print('OK:', app.title)"

sam-build:
	cd infrastructure && sam build

sam-deploy:
	cd infrastructure && sam deploy --config-env dev

sam-deploy-prod:
	cd infrastructure && sam deploy --config-env prod --no-confirm-changeset

setup-vapi:
	cd apps/api && SERVER_URL=$${SERVER_URL:-http://localhost:8000} .venv/bin/python ../../scripts/setup_vapi.py
