"""Reddit RSS B2C miner — no API key required."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.miners.buyer_intent import (
    market_from_subreddit,
    market_from_text,
    passes_buyer_filter,
    stable_lead_id,
)

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    "https://www.reddit.com/r/dubai+UAE+expats/search.rss?q=flight+ticket+travel+agent+cheap&sort=new&t=day",
    "https://www.reddit.com/r/india/search.rss?q=flight+ticket+travel+agent+cheap&sort=new&t=day",
    "https://www.reddit.com/r/unitedkingdom/search.rss?q=cheap+flight+india+dubai+travel+agent&sort=new&t=day",
    "https://www.reddit.com/r/australia/search.rss?q=cheap+flight+india+dubai+travel+agent&sort=new&t=day",
    "https://www.reddit.com/r/newjersey+nyc+chicago/search.rss?q=cheap+flight+india+dubai+travel+agent&sort=new&t=day",
    "https://www.reddit.com/r/travel/search.rss?q=cheap+flight+UAE+India+Dubai+agent&sort=new&t=day",
]

REDDIT_INTENT_RE = re.compile(
    r"\b(need flight|cheap flight|travel agent|book flight|flight ticket|"
    r"looking for flight|recommend agent|anyone know|best price|fly to|ticket to)\b",
    re.I,
)

USER_AGENT = "TravelAI-LeadMiner/2.0 (B2C RSS; contact: travel@travelai.com)"


async def mine_reddit_rss(limit: int = 200) -> tuple[list[dict[str, Any]], dict[str, int]]:
    leads: list[dict[str, Any]] = []
    stats = {"feeds_fetched": 0, "entries_checked": 0, "skipped": 0}

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for feed_url in RSS_FEEDS:
            try:
                resp = await client.get(feed_url, headers={"User-Agent": USER_AGENT})
                if resp.status_code != 200:
                    logger.warning("Reddit RSS %s returned %s", feed_url, resp.status_code)
                    continue
                stats["feeds_fetched"] += 1
                root = ET.fromstring(resp.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                entries = root.findall("atom:entry", ns) or root.findall("entry")
                for entry in entries:
                    stats["entries_checked"] += 1
                    title = _elem_text(entry, "title", ns)
                    summary = _elem_text(entry, "summary", ns) or _elem_text(entry, "content", ns)
                    link = _entry_link(entry, ns)
                    author_el = entry.find("atom:author", ns) or entry.find("author")
                    author = ""
                    if author_el is not None:
                        name_el = author_el.find("atom:name", ns) or author_el.find("name")
                        author = (name_el.text or "").strip() if name_el is not None else ""
                    published = _elem_text(entry, "published", ns) or _elem_text(entry, "updated", ns)
                    combined = f"{title}\n{summary}".strip()

                    if not REDDIT_INTENT_RE.search(combined):
                        stats["skipped"] += 1
                        continue
                    if not passes_buyer_filter(combined):
                        stats["skipped"] += 1
                        continue

                    subreddit = _subreddit_from_link(link) or _subreddit_from_feed(feed_url)
                    market = market_from_subreddit(subreddit) if subreddit else market_from_text(combined)
                    external_id = stable_lead_id("reddit_rss", link or combined[:120])

                    leads.append({
                        "name": author or "reddit_user",
                        "phone": "",
                        "source": "reddit_rss",
                        "source_detail": f"r/{subreddit}" if subreddit else "reddit_rss",
                        "external_id": external_id,
                        "lead_segment": "b2c",
                        "lead_category": "consumer",
                        "call_ready": True,
                        "post_url": link,
                        "contact_url": link,
                        "market": market,
                        "notes": combined[:500].strip(),
                        "opt_in_marketing": True,
                        "scored": False,
                        "status": "new",
                        "preferred_language": "en",
                        "message_at": published,
                    })
                    if len(leads) >= limit:
                        return _dedupe(leads), stats
            except Exception:
                logger.exception("Reddit RSS feed failed: %s", feed_url)

    return _dedupe(leads), stats


def _elem_text(entry: ET.Element, path: str, ns: dict[str, str]) -> str:
    if "/" in path:
        parts = path.split("/")
        node = entry
        for part in parts:
            node = node.find(f"atom:{part}", ns) or node.find(part)
            if node is None:
                return ""
        return (node.text or "").strip()
    node = entry.find(f"atom:{path}", ns) or entry.find(path)
    return (node.text or "").strip() if node is not None else ""


def _entry_link(entry: ET.Element, ns: dict[str, str]) -> str:
    for tag in ("atom:link", "link"):
        for link in entry.findall(tag, ns) if tag.startswith("atom:") else entry.findall(tag):
            href = link.get("href")
            if href and "reddit.com" in href:
                return href
    return ""


def _subreddit_from_link(link: str) -> str:
    m = re.search(r"/r/([^/]+)/", link or "")
    return m.group(1) if m else ""


def _subreddit_from_feed(feed_url: str) -> str:
    m = re.search(r"/r/([^/]+)/", feed_url)
    return m.group(1).split("+")[0] if m else ""


def _dedupe(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for lead in leads:
        key = lead.get("external_id") or lead.get("post_url") or ""
        if key and key not in seen:
            seen.add(key)
            out.append(lead)
    return out
