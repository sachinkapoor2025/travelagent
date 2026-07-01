# TravelAI Agent Portal — Quick Guide

**Live portal:** https://duao2n2qg02hl.cloudfront.net  
**Markets:** UAE · India

---

## What the portal does

| Area | What you can do |
|------|-----------------|
| **Dashboard** | See total leads, hot leads (score ≥ 80), contact rate, and 24h chat sessions at a glance. |
| **Create Lead** | Add a traveller by phone, route, and market. Optionally triggers an **AI voice callback** (Vapi). |
| **Leads Pipeline** | View all leads with score, status, and market. Click **Call** to start an outbound AI call. |
| **Web Chat (Sarah AI)** | Chat with the AI travel assistant for flights, hotels, and packages. |
| **Price Alerts** | Set a target fare for a route; the system notifies when price drops. |
| **Channel Breakdown** | See leads and activity split by source (website, WhatsApp, voice, etc.). |
| **Ad Intelligence** | Analyze route + market for ad copy and campaign ideas. |

---

## Platform capabilities (backend)

These run via API/webhooks even when not shown on the portal UI:

- **Voice AI** — inbound/outbound calls (Vapi + Twilio)
- **WhatsApp** — Meta Business API messaging
- **Flights** — search and quotes (Duffel)
- **Hotels** — search and recommendations
- **Itineraries** — AI-generated trip plans
- **Payments** — Stripe (UAE/international) and Razorpay (India)
- **SMS** — Twilio text follow-ups
- **Referrals** — referral codes and tracking
- **Email nurture** — automated follow-up sequences (SMTP)
- **Webhooks** — Stripe, Vapi, WhatsApp event handlers

---

## How to use (typical flow)

1. Open the portal URL in your browser.
2. **Create Lead** with phone + route → lead appears in the pipeline.
3. Use **Call** or enable opt-in voice on create → AI calls the customer.
4. Use **Web Chat** to test Sarah AI responses.
5. Watch **Dashboard** stats refresh every 15–30 seconds.

---

## URLs

| Purpose | URL |
|---------|-----|
| **Portal (use this)** | https://duao2n2qg02hl.cloudfront.net |
| **API (integrations only)** | https://0f43uh5wuf.execute-api.ap-south-1.amazonaws.com/prod |

---

## Notes

- Portal is static (CloudFront + S3); data comes from the API in the background.
- Cognito login is configured in AWS but not yet required on the portal UI.
- Voice, WhatsApp, payments, and flight search need API keys in GitHub/AWS secrets to work in production.
