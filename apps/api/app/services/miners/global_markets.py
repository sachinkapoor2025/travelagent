"""Worldwide travel hubs for B2B directory mining — batched by cursor index."""

from __future__ import annotations

# label, lat, lon, market_code (free-form country/region slug)
GLOBAL_MARKETS: list[tuple[str, float, float, str]] = [
    ("Dubai UAE", 25.2048, 55.2708, "uae"),
    ("Abu Dhabi UAE", 24.4539, 54.3773, "uae"),
    ("Mumbai India", 19.0760, 72.8777, "india"),
    ("Delhi India", 28.6139, 77.2090, "india"),
    ("Bangalore India", 12.9716, 77.5946, "india"),
    ("London UK", 51.5074, -0.1278, "uk"),
    ("Manchester UK", 53.4808, -2.2426, "uk"),
    ("New York USA", 40.7128, -74.0060, "us"),
    ("Los Angeles USA", 34.0522, -118.2437, "us"),
    ("Chicago USA", 41.8781, -87.6298, "us"),
    ("Toronto Canada", 43.6532, -79.3832, "ca"),
    ("Vancouver Canada", 49.2827, -123.1207, "ca"),
    ("Sydney Australia", -33.8688, 151.2093, "au"),
    ("Melbourne Australia", -37.8136, 144.9631, "au"),
    ("Singapore", 1.3521, 103.8198, "sg"),
    ("Bangkok Thailand", 13.7563, 100.5018, "th"),
    ("Kuala Lumpur Malaysia", 3.1390, 101.6869, "my"),
    ("Jakarta Indonesia", -6.2088, 106.8456, "id"),
    ("Manila Philippines", 14.5995, 120.9842, "ph"),
    ("Hong Kong", 22.3193, 114.1694, "hk"),
    ("Tokyo Japan", 35.6762, 139.6503, "jp"),
    ("Seoul South Korea", 37.5665, 126.9780, "kr"),
    ("Paris France", 48.8566, 2.3522, "fr"),
    ("Frankfurt Germany", 50.1109, 8.6821, "de"),
    ("Amsterdam Netherlands", 52.3676, 4.9041, "nl"),
    ("Rome Italy", 41.9028, 12.4964, "it"),
    ("Madrid Spain", 40.4168, -3.7038, "es"),
    ("Istanbul Turkey", 41.0082, 28.9784, "tr"),
    ("Cairo Egypt", 30.0444, 31.2357, "eg"),
    ("Johannesburg South Africa", -26.2041, 28.0473, "za"),
    ("Nairobi Kenya", -1.2921, 36.8219, "ke"),
    ("Riyadh Saudi Arabia", 24.7136, 46.6753, "sa"),
    ("Doha Qatar", 25.2854, 51.5310, "qa"),
    ("Kuwait City", 29.3759, 47.9774, "kw"),
    ("Muscat Oman", 23.5880, 58.3829, "om"),
    ("Tel Aviv Israel", 32.0853, 34.7818, "il"),
    ("São Paulo Brazil", -23.5505, -46.6333, "br"),
    ("Mexico City Mexico", 19.4326, -99.1332, "mx"),
    ("Buenos Aires Argentina", -34.6037, -58.3816, "ar"),
    ("Auckland New Zealand", -36.8485, 174.7633, "nz"),
]


def market_batch(cursor: int, batch_size: int = 5) -> tuple[list[tuple[str, float, float, str]], int, bool]:
    """Return slice of markets, next cursor, and whether mining is complete."""
    total = len(GLOBAL_MARKETS)
    if cursor >= total:
        return [], total, True
    chunk = GLOBAL_MARKETS[cursor : cursor + batch_size]
    next_cursor = cursor + len(chunk)
    complete = next_cursor >= total
    return chunk, next_cursor, complete
