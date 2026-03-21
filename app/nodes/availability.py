"""
Availability Node — runs once (passes through if slots already fetched).

Detects urgency tier from the current time/day and loads the matching
availability slots from the stub availability.json file.
No real calendar integration — fully stubbed for the demo.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict

from app.config import load_availability, load_business_config, resolve_slot_dates
from app.state import QuoteState


def _detect_urgency_tier() -> str:
    """Determine urgency tier from current system time."""
    now = datetime.datetime.now()
    hour = now.hour
    is_weekend = now.weekday() >= 5  # Saturday=5, Sunday=6
    is_evening = hour >= 18

    if is_weekend or is_evening:
        return "evening_weekend"
    elif hour >= 8:
        return "same_day"
    else:
        return "next_day"


def availability_node(state: QuoteState) -> Dict[str, Any]:
    # Pass through — slots already fetched
    if state.get("availability_slots"):
        return {}

    config = load_business_config()
    availability_data = load_availability()

    # Use state urgency_tier if already set (e.g. detected from conversation),
    # otherwise auto-detect from current time.
    urgency_tier = state.get("urgency_tier") or _detect_urgency_tier()
    tier_config = config["urgency_tiers"].get(urgency_tier, {})
    multiplier = float(tier_config.get("multiplier", 1.0))

    raw_slots = availability_data["slots"].get(urgency_tier, [])[:3]
    slots = resolve_slot_dates(raw_slots)

    return {
        "urgency_tier": urgency_tier,
        "urgency_multiplier": multiplier,
        "availability_slots": slots,
    }
