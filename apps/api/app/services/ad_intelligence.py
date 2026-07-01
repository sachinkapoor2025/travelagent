"""AI-powered ad intelligence — 3-stage fetch, analyse, generate pipeline."""

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings
from app.models import Market
from app.schemas import AdAnalysisResponse, AdVariant, GeneratedAdPackage
from app.services.ad_sources import ad_sources

settings = get_settings()
logger = logging.getLogger(__name__)

AD_GENERATION_PROMPT = """You are a world-class travel advertising strategist targeting UAE + India diaspora travellers.
Analyse competitor ads and generate a superior travel ad package.

Return JSON with:
- competitor_insights: list of 5 insights
- winning_patterns: list of 5 patterns
- gap_analysis: list of 3 gaps competitors miss
- ad_variants: list of 5 objects with headline, description, cta, predicted_ctr_score (0-1), rationale
- generated_package: object with hook, body_copy, offer_usp, cta, target_persona, visual_description,
  headline_ar, headline_hi, cta_ar, cta_hi"""


class AdIntelligenceService:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def analyze_route(self, origin: str, destination: str, market: Market, platform: str = "google") -> AdAnalysisResponse:
        fetched = await ad_sources.fetch_all(origin, destination, market)
        competitors = fetched.get("ads", [])
        return await self._analyze_and_generate(origin, destination, market, platform, competitors)

    async def fetch_competitor_ads(self, origin: str, destination: str, market: Market) -> dict[str, Any]:
        return await ad_sources.fetch_all(origin, destination, market)

    async def generate_superior_ad(self, origin: str, destination: str, market: Market) -> GeneratedAdPackage:
        analysis = await self.analyze_route(origin, destination, market)
        if analysis.generated_package:
            return analysis.generated_package
        return GeneratedAdPackage(
            hook=f"Fly {origin}→{destination} smarter with Sarah AI",
            body_copy="Skip the search chaos. Our AI finds the best fare in 60 seconds.",
            offer_usp="Best price guarantee + free date change on select airlines",
            cta="Book with Sarah",
            target_persona="UAE/India diaspora booking international flights",
            visual_description=f"Split screen: {origin} skyline and {destination} landmark with Sarah AI chat overlay",
            headline_ar="احجز رحلتك بأفضل سعر",
            headline_hi="सबसे सस्ता टिकट — AI से बुक करें",
            cta_ar="احجز الآن",
            cta_hi="अभी बुक करें",
        )

    async def _analyze_and_generate(
        self,
        origin: str,
        destination: str,
        market: Market,
        platform: str,
        competitors: list[dict[str, Any]],
    ) -> AdAnalysisResponse:
        competitor_text = "\n".join(
            f"[{c.get('source', '?')}] {c.get('advertiser', 'Unknown')}: {c.get('headline', c.get('title', 'N/A'))} — {c.get('body', c.get('description', ''))}"
            for c in competitors[:20]
        )

        if self.client:
            try:
                prompt = f"""Route: {origin} to {destination} ({market.value}, {platform})

Competitor ads:
{competitor_text}

{AD_GENERATION_PROMPT}"""

                response = await self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.7,
                    timeout=25.0,
                )
                data = json.loads(response.choices[0].message.content or "{}")
                variants: list[AdVariant] = []
                for item in data.get("ad_variants", []):
                    try:
                        variants.append(
                            AdVariant(
                                headline=str(item.get("headline", f"{origin}→{destination}")),
                                description=str(item.get("description", "Book with Sarah AI")),
                                cta=str(item.get("cta", "Book Now")),
                                predicted_ctr_score=float(item.get("predicted_ctr_score", 0.7)),
                                rationale=str(item.get("rationale", "AI-generated")),
                            )
                        )
                    except (TypeError, ValueError):
                        continue
                if not variants:
                    return self._fallback_analysis(origin, destination, market, competitors)
                pkg_data = data.get("generated_package") or {}
                generated = None
                if pkg_data.get("hook"):
                    try:
                        generated = GeneratedAdPackage(**pkg_data)
                    except Exception:
                        generated = None
                return AdAnalysisResponse(
                    route=f"{origin}-{destination}",
                    market=market,
                    competitor_insights=data.get("competitor_insights", []) or [],
                    winning_patterns=data.get("winning_patterns", []) or [],
                    gap_analysis=data.get("gap_analysis", []) or [],
                    ad_variants=variants,
                    competitor_ads=competitors[:10],
                    generated_package=generated,
                )
            except Exception:
                logger.exception("OpenAI ad analysis failed for %s-%s", origin, destination)

        return self._fallback_analysis(origin, destination, market, competitors)

    def _fallback_analysis(
        self, origin: str, destination: str, market: Market, competitors: list[dict[str, Any]]
    ) -> AdAnalysisResponse:
        currency = "AED" if market == Market.UAE else "₹"
        base = self._fallback_analysis_legacy(origin, destination, market, competitors)
        base.competitor_ads = competitors[:10]
        base.gap_analysis = [
            "No competitor emphasizes AI voice booking in Arabic/Hindi",
            "Payment localization (UPI/RuPay) underused in headlines",
            "Post-booking disruption support missing from competitor copy",
        ]
        base.generated_package = GeneratedAdPackage(
            hook=f"{origin}→{destination} — Sarah finds your fare in 60 sec",
            body_copy=f"Beat every OTA price from {currency}899. AI assistant in English, Arabic, Hindi.",
            offer_usp="Live Duffel inventory + instant WhatsApp booking link",
            cta="Talk to Sarah",
            target_persona=f"{market.value.upper()} diaspora flying {origin}-{destination}",
            visual_description="Female AI travel agent on phone with flight map overlay",
            headline_ar="سفر ذكي بأفضل الأسعار",
            headline_hi="AI से सस्ती उड़ान बुक करें",
            cta_ar="اتصل الآن",
            cta_hi="अभी कॉल करें",
        )
        return base

    def _fallback_analysis_legacy(
        self, origin: str, destination: str, market: Market, competitors: list[dict[str, Any]]
    ) -> AdAnalysisResponse:
        currency = "AED" if market == Market.UAE else "₹"
        return AdAnalysisResponse(
            route=f"{origin}-{destination}",
            market=market,
            competitor_insights=[
                "Price-led headlines dominate SERP for this route",
                "Urgency messaging appears in 60% of top ads",
                "Free cancellation is a common trust signal",
                "Direct flight emphasis wins for business travelers",
                "Bundle offers appear for leisure destinations",
            ],
            winning_patterns=[
                "Specific price anchor in headline",
                f"Route clarity ({origin} → {destination})",
                "Urgency without being spammy",
                "Trust badge (IATA, secure booking)",
                "Localized currency and payment methods",
            ],
            ad_variants=[
                AdVariant(
                    headline=f"{origin}→{destination} from {currency}899",
                    description="Direct & 1-stop flights. Amex, RuPay, UPI. Book in 2 mins with AI.",
                    cta="Book Now",
                    predicted_ctr_score=0.82,
                    rationale="Price anchor + payment localization",
                ),
                AdVariant(
                    headline=f"Fly {destination} — Save 20%",
                    description="AI finds cheapest fares. Free date change on select airlines.",
                    cta="Search Flights",
                    predicted_ctr_score=0.78,
                    rationale="Discount + AI differentiation",
                ),
                AdVariant(
                    headline=f"Direct Flights {origin} {destination}",
                    description="Emirates, Qatar, IndiGo compared. 24/7 AI booking.",
                    cta="Compare Fares",
                    predicted_ctr_score=0.75,
                    rationale="Direct flight intent match",
                ),
                AdVariant(
                    headline=f"{destination} — Last Seats",
                    description=f"From {currency}899. Secure checkout. Call Sarah AI.",
                    cta="Grab Deal",
                    predicted_ctr_score=0.71,
                    rationale="Scarcity + omnichannel",
                ),
                AdVariant(
                    headline=f"Smart Travel to {destination}",
                    description="3 best options in 60 seconds. Arabic, Hindi, English support.",
                    cta="Talk to Sarah",
                    predicted_ctr_score=0.69,
                    rationale="Multilingual AI moat",
                ),
            ],
        )


ad_intelligence = AdIntelligenceService()
