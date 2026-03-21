"""
Postcode Capture Node — runs when phase="awaiting_postcode".

Reads the latest human message, extracts a UK postcode district via regex
(zero LLM cost), and updates state so pricing can recalculate with the correct
ULEZ surcharge.

On success: clears calculated_price/final_price so pricing_node re-runs.
On failure: sets a carrier asking the customer to try again (stays awaiting_postcode).
"""
from __future__ import annotations

import re
from typing import Any, Dict

from app.state import QuoteState

# Matches full postcodes (SW1A 1AA) or district-only (SW1A, E14, NW3)
_UK_POSTCODE_RE = re.compile(
    r"\b([A-Z]{1,2}[0-9][0-9A-Z]?)(?:\s*[0-9][A-Z]{2})?\b",
    re.IGNORECASE,
)

# Area codes (leading letters) that belong to London postcodes
_LONDON_AREAS = {"E", "EC", "N", "NW", "SE", "SW", "W", "WC"}


def _is_london_postcode(district: str) -> bool:
    """Return True if the postcode district's area code is a London area."""
    m = re.match(r'^([A-Z]+)', district.upper())
    return bool(m) and m.group(1) in _LONDON_AREAS


def postcode_capture_node(state: QuoteState) -> Dict[str, Any]:
    messages = state.get("messages", [])

    latest: str | None = None
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "human":
            latest = msg.content
            break

    if latest:
        match = _UK_POSTCODE_RE.search(latest)
        if match:
            postcode = match.group(0).strip().upper()

            # Validate it's actually a London postcode
            if not _is_london_postcode(postcode):
                return {
                    "next_diagnostic_question": (
                        f"That looks like a valid UK postcode, but we only cover London. "
                        "Could you double-check? We serve E, N, NW, SE, SW, W, WC, and EC postcodes."
                    ),
                    "phase": "awaiting_postcode",
                }

            # Clear current price so pricing_node re-runs with correct ULEZ zone
            return {
                "postcode": postcode,
                "calculated_price": None,
                "final_price": None,
                "ulez_zone": None,
                "ulez_surcharge": 0.0,
            }

    # Couldn't find a postcode — ask again via carrier
    return {
        "next_diagnostic_question": (
            "I couldn't spot a postcode in that — could you share it? "
            "For example: SW1A, E14, or NW3."
        ),
        "phase": "awaiting_postcode",
    }
