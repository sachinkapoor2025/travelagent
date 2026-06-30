# TravelAI Agent

Full-stack AI travel agent platform for **UAE** and **India** markets. Voice calling, WhatsApp, web chat, SMS, lead generation, flight/hotel booking, packages, itineraries, price alerts, referrals, and AI ad intelligence — deployable on AWS via SAM + GitHub Actions.

## Features

| Feature | Description |
|---------|-------------|
| **Voice Agent (Sarah)** | Human-like AI phone agent — language selection, flight search, Q&A, booking, payment link |
| **Web Chat Agent** | Embeddable website chat — same Sarah brain, session memory, suggested actions |
| **WhatsApp Agent** | Qualify leads, quote flights, send payment links |
| **SMS Agent** | Two-way SMS via Twilio — same conversational AI |
| **Lead Engine** | Auto-scoring, 60-second callback, hot/warm/cold pipeline, DNC registry |
| **Meta/Google Webhooks** | Auto-ingest leads from Facebook Lead Ads & Google Ads forms |
| **Flight Booking** | Duffel API integration (sandbox + production) |
| **Hotels & Packages** | Hotel search + curated UAE/India holiday packages |
| **Itinerary Builder** | AI-generated day-by-day travel plans |
| **Price Alerts** | Notify via WhatsApp when flight price drops below target |
| **Referral Program** | Viral growth — share codes, earn AED/INR rewards |
| **Email Nurture** | Abandoned search recovery emails (scheduled worker) |
| **Payments** | Stripe (UAE/global) + Razorpay (India: RuPay, UPI) |
| **Ad Intelligence** | Analyze competitor ads, generate winning variants with AI |
| **Analytics Dashboard** | Conversion funnel, channel breakdown, contact rates |
| **Compliance** | UAE TDRA calling hours, India timezone, opt-in, DNC |
| **Admin Dashboard** | Web UI at `/dashboard` |

## Quick Start

### 1. Clone and configure

```bash
cd ~/Projects/travel-ai-agent
cp .env.example .env
# Edit .env with your API keys
```

### 2. Run with Docker

```bash
docker compose up --build
```

API: http://localhost:8000  
Docs: http://localhost:8000/docs  
Dashboard: http://localhost:8000/dashboard

### 3. Run locally (without Docker)

```bash
make install
make dev
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/leads` | Create lead (+ auto callback) |
| POST | `/api/v1/leads/{id}/call` | Trigger AI outbound call |
| POST | `/api/v1/chat` | Web chat with Sarah AI |
| POST | `/api/v1/flights/search` | Search flights |
| POST | `/api/v1/flights/book` | Create booking |
| POST | `/api/v1/hotels/search` | Search hotels |
| POST | `/api/v1/hotels/packages/search` | Search holiday packages |
| POST | `/api/v1/itineraries` | Generate AI itinerary |
| POST | `/api/v1/price-alerts` | Set flight price alert |
| POST | `/api/v1/referrals/register` | Get referral code |
| POST | `/api/v1/referrals/apply` | Apply referral code |
| GET | `/api/v1/analytics/dashboard` | Funnel & channel stats |
| POST | `/api/v1/webhooks/meta-leads` | Meta Lead Ads webhook |
| POST | `/api/v1/webhooks/google-leads` | Google Ads lead webhook |
| POST | `/api/v1/sms/webhook` | Twilio SMS webhook |
| POST | `/api/v1/voice/webhook` | Vapi tool-call webhook |
| POST | `/api/v1/whatsapp/webhook` | WhatsApp incoming messages |
| POST | `/api/v1/ads/analyze` | Competitor ad analysis |

## AWS Deployment (SAM)

Same pattern as hr-ecom — `template.yaml` + `samconfig.toml`:

```bash
cd infrastructure
sam build
sam deploy --config-env dev
```

Production:

```bash
make sam-deploy-prod
```

GitHub secrets needed (see `.github/workflows/deploy.yml`):
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- `OPENAI_API_KEY`, `VAPI_API_KEY`, `VAPI_ASSISTANT_ID`
- `DUFFEL_API_TOKEN`, `STRIPE_SECRET_KEY`, `RAZORPAY_KEY_ID`
- `WHATSAPP_ACCESS_TOKEN`, `TWILIO_ACCOUNT_SID`, `SMTP_PASSWORD`

Push to `main` → CI tests → SAM deploy to `me-central-1`.

## GitHub Actions — AWS credentials fix

If deploy fails with **"The security token included in the request is invalid"**:

1. **Use permanent IAM keys only** — access key must start with `AKIA` (not `ASIA`).
2. In GitHub → **Settings → Secrets and variables → Actions**, set exactly:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
3. **Do not set** `AWS_SESSION_TOKEN` unless you use temporary/SSO keys (`ASIA...`).
4. If `AWS_SESSION_TOKEN` exists as an org-level secret, delete it or override it for this repo.
5. Re-create IAM access keys if they were rotated or deactivated in AWS Console.

The updated `deploy.yml` clears stale session tokens and runs `aws sts get-caller-identity` before SAM deploy.

## Project Structure

```
travel-ai-agent/
├── apps/api/              # FastAPI backend
│   ├── app/
│   │   ├── routers/       # API routes
│   │   ├── services/      # Voice, chat, booking, leads, hotels, etc.
│   │   ├── storage/       # DynamoDB layer (AWS SAM)
│   │   └── static/        # Admin dashboard
│   ├── lambda_handler.py  # AWS Lambda entry (Mangum)
│   └── scheduled_handler.py
├── infrastructure/        # AWS SAM (template.yaml, samconfig.toml)
├── scripts/               # Setup helpers
└── .github/workflows/     # CI + SAM deploy
```

## License

Proprietary — TravelAI 


