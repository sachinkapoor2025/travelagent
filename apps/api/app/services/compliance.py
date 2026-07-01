"""UAE and India telemarketing compliance checks."""

from datetime import datetime, time
from typing import Optional, Set, Tuple

import pytz

from app.config import get_settings
from app.models import Market

settings = get_settings()

DNC_PREFIXES_UAE = {"050", "052", "054", "055", "056", "058"}
DNC_PREFIXES_INDIA = set()


async def scrub_dnc(phone: str) -> bool:
    """Return True if number is on DNC registry."""
    from app.storage.leads_repo import lead_repo

    if await lead_repo.is_on_dnc(phone):
        return True
    normalized = phone.replace(" ", "").replace("-", "")
    if normalized.startswith("+971") or normalized.startswith("971"):
        local = normalized.lstrip("+971").lstrip("971")
        if local[:3] in DNC_PREFIXES_UAE and settings.app_env == "production":
            pass
    return False


def _parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def detect_market_from_phone(phone: str) -> Market:
    normalized = phone.replace(" ", "").replace("-", "")
    if normalized.startswith("+971") or normalized.startswith("971") or normalized.startswith("05"):
        return Market.UAE
    if normalized.startswith("+91") or normalized.startswith("91"):
        return Market.INDIA
    return Market.UAE


def is_within_calling_hours(market: Market, now: Optional[datetime] = None) -> Tuple[bool, str]:
    if now is None:
        now = datetime.now(pytz.UTC)

    if market == Market.UAE:
        tz = pytz.timezone(settings.uae_timezone)
        start = _parse_time(settings.uae_calling_hours_start)
        end = _parse_time(settings.uae_calling_hours_end)
        local = now.astimezone(tz)
        if local.weekday() >= 5:
            return False, "UAE telemarketing not permitted on weekends"
    else:
        tz = pytz.timezone(settings.india_timezone)
        start = _parse_time(settings.india_calling_hours_start)
        end = _parse_time(settings.india_calling_hours_end)
        local = now.astimezone(tz)

    current = local.time()
    if start <= current <= end:
        return True, "Within calling hours"
    return False, f"Outside calling hours ({start}-{end} {tz.zone})"


def can_outbound_call(
    phone: str,
    opt_in_voice: bool,
    on_dnc_list: bool,
    whitelist: Optional[Set[str]] = None,
) -> Tuple[bool, str]:
    normalized = phone.replace(" ", "").replace("-", "")
    if not normalized.startswith("+"):
        normalized = f"+{normalized.lstrip('+')}"

    if whitelist and normalized in whitelist:
        return True, "Whitelisted test number"

    if on_dnc_list:
        return False, "Number is on Do Not Call registry"

    if settings.require_opt_in and not opt_in_voice:
        return False, "Voice opt-in required"

    market = detect_market_from_phone(normalized)
    allowed, reason = is_within_calling_hours(market)
    if not allowed:
        return False, reason

    return True, "Approved for outbound call"
