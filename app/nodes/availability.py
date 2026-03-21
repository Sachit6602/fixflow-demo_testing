"""
Availability Node — runs once (passes through if slots already fetched).

Detects urgency tier from the current time/day, then generates availability
slots based on engineer schedules and estimated travel time to the customer's
postcode (via postcodes.io).

Falls back to static slots from availability.json if the customer postcode
is missing or geocoding fails.
"""
from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional

from app.config import load_availability, load_business_config, load_engineers
from app.geo import travel_time_between_postcodes
from app.state import QuoteState

# UK postcode pattern (e.g., "N1 3LL", "SE1 7PB", "E2 0SY", "EC1A 1BB")
_POSTCODE_RE = re.compile(
    r'\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b',
    re.IGNORECASE,
)


def _detect_urgency_tier() -> str:
    """Determine urgency tier from current system time."""
    now = datetime.datetime.now()
    hour = now.hour
    is_weekend = now.weekday() >= 5

    if is_weekend or hour >= 18:
        return "evening_weekend"
    elif hour >= 8:
        return "same_day"
    else:
        return "next_day"


def _resolve_slot_dates(slots: list) -> list:
    """Replace 'today'/'tomorrow' strings with human-readable dates."""
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    date_map = {
        "today": today.strftime("%A %d %B").replace(" 0", " "),
        "tomorrow": tomorrow.strftime("%A %d %B").replace(" 0", " "),
    }
    resolved = []
    for slot in slots:
        s = dict(slot)
        s["date"] = date_map.get(s.get("date", ""), s.get("date", ""))
        resolved.append(s)
    return resolved


def _extract_postcode_from_messages(messages: list) -> Optional[str]:
    """Try to extract a UK postcode from conversation messages."""
    for msg in reversed(messages):
        text = getattr(msg, "content", "")
        match = _POSTCODE_RE.search(text)
        if match:
            return match.group(1).upper()
    return None


def _get_operating_window(dt: datetime.datetime, operating_hours: dict) -> tuple:
    """Return (start_time, end_time) as datetime objects for the given day."""
    is_weekend = dt.weekday() >= 5
    hours = operating_hours.get("weekend" if is_weekend else "weekday", {})
    start_h, start_m = map(int, hours.get("start", "07:00").split(":"))
    end_h, end_m = map(int, hours.get("end", "22:00").split(":"))
    start = dt.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = dt.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    return start, end


def _build_dynamic_slots(customer_postcode: str) -> List[Dict[str, Any]]:
    """
    Build availability slots from engineer schedules + travel time.

    Returns unique time slots (no duplicates for the same hour), sorted by
    earliest arrival, limited to 3.
    """
    engineers_data = load_engineers()
    operating_hours = engineers_data.get("operating_hours", {})
    now = datetime.datetime.now()

    # Collect all possible arrival slots across all engineers
    all_slots = []

    for eng in engineers_data["engineers"]:
        for slot_entry in eng.get("schedule", []):
            # Parse the schedule entry
            slot_date = datetime.datetime.strptime(slot_entry["date"], "%Y-%m-%d")
            avail_h, avail_m = map(int, slot_entry["available_from"].split(":"))
            available_from = slot_date.replace(hour=avail_h, minute=avail_m, second=0, microsecond=0)

            # Skip slots in the past
            if available_from < now:
                continue

            # Calculate travel time from this slot's location
            travel_mins = travel_time_between_postcodes(slot_entry.get("location", ""), customer_postcode)
            if travel_mins is None:
                continue

            # Calculate arrival time, rounded up to nearest 10 minutes
            arrival_time = available_from + datetime.timedelta(minutes=travel_mins)
            remainder = arrival_time.minute % 10
            if remainder:
                arrival_time += datetime.timedelta(minutes=10 - remainder)
                arrival_time = arrival_time.replace(second=0, microsecond=0)

            # Enforce operating hours
            day_start, day_end = _get_operating_window(arrival_time, operating_hours)
            if arrival_time < day_start:
                arrival_time = day_start
            if arrival_time > day_end:
                continue  # Skip — too late for this day

            all_slots.append({
                "arrival_time": arrival_time,
                "engineer_id": eng["engineer_id"],
            })

    # Sort by earliest arrival
    all_slots.sort(key=lambda s: s["arrival_time"])

    # De-duplicate by hour (keep first engineer for each unique hour slot)
    seen_hours = set()
    unique_slots = []
    for s in all_slots:
        hour_key = s["arrival_time"].strftime("%Y-%m-%d %H:00")
        if hour_key in seen_hours:
            continue
        seen_hours.add(hour_key)
        unique_slots.append(s)
        if len(unique_slots) >= 3:
            break

    # Format as slot dicts
    formatted = []
    for i, s in enumerate(unique_slots):
        arrival = s["arrival_time"]
        date_str = arrival.strftime("%d %B")
        # Remove leading zero from day
        if date_str.startswith("0"):
            date_str = date_str[1:]
        time_str = arrival.strftime("%H:%M")

        formatted.append({
            "id": f"dyn_{i+1}",
            "date": date_str,
            "time": time_str,
        })

    return formatted


def availability_node(state: QuoteState) -> Dict[str, Any]:
    # Pass through — slots already fetched
    if state.get("availability_slots"):
        return {}

    config = load_business_config()

    urgency_tier = state.get("urgency_tier") or _detect_urgency_tier()
    tier_config = config["urgency_tiers"].get(urgency_tier, {})
    multiplier = float(tier_config.get("multiplier", 1.0))

    # Try dynamic slots if customer postcode is available
    customer_postcode = state.get("postcode")
    if not customer_postcode:
        customer_postcode = _extract_postcode_from_messages(state.get("messages", []))

    slots = []

    if customer_postcode:
        try:
            slots = _build_dynamic_slots(customer_postcode)
        except Exception as e:
            print(f"[Availability] Dynamic slots failed, falling back to static: {e}")
            slots = []

    # Fallback to static slots
    if not slots:
        availability_data = load_availability()
        raw_slots = availability_data["slots"].get(urgency_tier, [])[:3]
        slots = _resolve_slot_dates(raw_slots)

    return {
        "urgency_tier": urgency_tier,
        "urgency_multiplier": multiplier,
        "availability_slots": slots,
    }
