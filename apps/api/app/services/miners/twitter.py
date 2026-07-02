"""Twitter/X B2C miner — free API v2 recent search."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.services.miners.buyer_intent import (
    market_from_text,
    passes_buyer_filter,
    stable_lead_id,
)

settings = get_settings()
logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    '("cheap flight") (dubai OR UAE OR india) -is:retweet lang:en',
    '("travel agent") (dubai OR UAE OR london) -is:retweet lang:en',
    '("need flight") (india OR dubai OR london) -is:retweet lang:en',
    '("ticket chahiye" OR "sasta ticket") -is:retweet',
    '("book flight") (india OR dubai OR australia) -is:retweet lang:en',
    '("flight se" OR "flight ka" OR "flight lena") -is:retweet',
]

TWITTER_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


async def mine_twitter(limit: int = 200) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    warnings: list[str] = []
    stats = {"queries_run": 0, "tweets_checked": 0, "skipped": 0}
    leads: list[dict[str, Any]] = []

    if not settings.twitter_bearer_token:
        return [], stats, ["Add TWITTER_BEARER_TOKEN to GitHub Secrets (free tier at developer.twitter.com)."]

    headers = {"Authorization": f"Bearer {settings.twitter_bearer_token}"}
    seen_ids: set[str] = set()

    async with httpx.AsyncClient(timeout=30.0) as client:
        for query in SEARCH_QUERIES:
            try:
                resp = await client.get(
                    TWITTER_SEARCH_URL,
                    headers=headers,
                    params={
                        "query": query,
                        "max_results": 100,
                        "tweet.fields": "author_id,created_at,text,lang",
                        "expansions": "author_id",
                        "user.fields": "name,username,location",
                    },
                )
                stats["queries_run"] += 1
                if resp.status_code == 401:
                    return [], stats, ["Twitter Bearer Token invalid or expired."]
                if resp.status_code == 429:
                    warnings.append("Twitter rate limit hit — try again later.")
                    break
                if resp.status_code != 200:
                    logger.warning("Twitter search failed: %s %s", resp.status_code, resp.text[:200])
                    continue

                data = resp.json()
                users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

                for tweet in data.get("data", []):
                    stats["tweets_checked"] += 1
                    tweet_id = tweet.get("id", "")
                    if tweet_id in seen_ids:
                        continue
                    seen_ids.add(tweet_id)

                    text = tweet.get("text", "")
                    if not passes_buyer_filter(text):
                        stats["skipped"] += 1
                        continue

                    author_id = tweet.get("author_id", "")
                    user = users.get(author_id, {})
                    username = user.get("username", "user")
                    display_name = user.get("name", username)
                    location = user.get("location", "")
                    market = market_from_text(f"{location} {text}")
                    profile_url = f"https://twitter.com/{username}"
                    post_url = f"https://twitter.com/{username}/status/{tweet_id}"
                    external_id = stable_lead_id("twitter", tweet_id)

                    leads.append({
                        "name": display_name,
                        "phone": "",
                        "source": "twitter",
                        "source_detail": f"@{username}",
                        "external_id": external_id,
                        "lead_segment": "b2c",
                        "lead_category": "consumer",
                        "call_ready": True,
                        "post_url": post_url,
                        "contact_url": profile_url,
                        "market": market,
                        "notes": text[:500],
                        "opt_in_marketing": True,
                        "scored": False,
                        "status": "new",
                        "preferred_language": "hi" if tweet.get("lang") == "hi" else "en",
                        "message_at": tweet.get("created_at"),
                    })
                    if len(leads) >= limit:
                        return leads, stats, warnings
            except Exception:
                logger.exception("Twitter query failed: %s", query)

    return leads, stats, warnings
