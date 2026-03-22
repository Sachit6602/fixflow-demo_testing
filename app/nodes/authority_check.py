"""
Authority Check — runs on every turn after a price exists.

Enforces the three-tier authority model from business_config.json:
  auto_confirm  — price < auto_confirm_below
  human_review  — price between human_review_min and human_review_max
  hard_block    — price > hard_block_above OR escalation_flag is set

This node is intentionally simple and deterministic — no LLM involved.
Authority limits are structural, not prompt-based.
"""
from __future__ import annotations

from typing import Any, Dict

from app.config import load_business_config
from app.state import QuoteState


def authority_check_node(state: QuoteState) -> Dict[str, Any]:
    # Escalations (e.g. boiler replacement) are always hard-blocked
    # regardless of price — this cannot be negotiated away.
    if state.get("escalation_flag"):
        return {"authority_level": "hard_block"}

    config = load_business_config()
    thresholds = config["authority_thresholds"]

    # Use final_price (post-negotiation) if available, else calculated_price
    price = state.get("final_price") or state.get("calculated_price") or 0.0

    if price < thresholds["auto_confirm_below"]:
        level = "auto_confirm"
    elif price <= thresholds["human_review_max"]:
        level = "human_review"
    else:
        level = "hard_block"

    return {"authority_level": level}
