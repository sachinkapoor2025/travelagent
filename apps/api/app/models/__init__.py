"""Domain enums — no SQLAlchemy (DynamoDB-only storage)."""

import enum


class Market(str, enum.Enum):
    UAE = "uae"
    INDIA = "india"
    UK = "uk"
    US = "us"
    AU = "au"


class LeadStatus(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    QUOTED = "quoted"
    BOOKING = "booking"
    WON = "won"
    LOST = "lost"
    DNC = "dnc"


class LeadSource(str, enum.Enum):
    WEBSITE = "website"
    WHATSAPP = "whatsapp"
    VOICE_INBOUND = "voice_inbound"
    VOICE_OUTBOUND = "voice_outbound"
    GOOGLE_ADS = "google_ads"
    META_ADS = "meta_ads"
    REFERRAL = "referral"
    ABANDONED_SEARCH = "abandoned_search"
    PARTNER = "partner"
    CLAY = "clay"
    APOLLO = "apollo"
    LINKEDIN = "linkedin"
    MANUAL = "manual"
    REDDIT = "reddit"
    TELEGRAM = "telegram"
    DIRECTORIES = "directories"


class CallDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class BookingStatus(str, enum.Enum):
    PENDING = "pending"
    HELD = "held"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentProvider(str, enum.Enum):
    STRIPE = "stripe"
    RAZORPAY = "razorpay"


class Language(str, enum.Enum):
    EN = "en"
    AR = "ar"
    HI = "hi"
    UR = "ur"
