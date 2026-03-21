"""
Pricing Node — runs once (passes through if calculated_price is already set).

Price formula:
  calculated_price = (base_price × urgency_multiplier) + ulez_surcharge + parts_estimate

ULEZ zone is derived from the postcode stored in state (fully defined in
business_config.json — no external API required for the demo).
"""
from __future__ import annotations

from typing import Any, Dict

from app.config import get_ulez_surcharge, get_ulez_zone, load_business_config
from app.state import QuoteState


def pricing_node(state: QuoteState) -> Dict[str, Any]:
    # Pass through — already priced
    if state.get("calculated_price") is not None:
        return {}

    config = load_business_config()
    job_type = state.get("job_type")
    confidence = state.get("confidence_level", "medium")
    urgency_multiplier = state.get("urgency_multiplier", 1.0)
    postcode = state.get("postcode")

    if not job_type or job_type not in config["supported_job_types"]:
        return {"error_state": f"pricing: unknown job type '{job_type}'"}

    job_cfg = config["supported_job_types"][job_type]

    # ── Base price by confidence ──────────────────────────────────────────────
    if confidence == "high":
        base_price = float(job_cfg["base_price"])
    elif confidence == "medium":
        lo, hi = job_cfg["price_range_medium"]
        base_price = float((lo + hi) / 2)
    else:  # low
        lo, hi = job_cfg["price_range_low"]
        base_price = float((lo + hi) / 2)

    # ── ULEZ surcharge ────────────────────────────────────────────────────────
    ulez_zone = "outside"
    ulez_surcharge = 0.0
    if postcode:
        ulez_zone = get_ulez_zone(postcode)
        ulez_surcharge = get_ulez_surcharge(ulez_zone)

    # ── Parts estimate ────────────────────────────────────────────────────────
    parts_estimate = (
        float(job_cfg.get("typical_parts_estimate", 0))
        if job_cfg.get("includes_parts")
        else 0.0
    )

    # ── Final calculation ─────────────────────────────────────────────────────
    calculated = round((base_price * urgency_multiplier) + ulez_surcharge + parts_estimate, 2)

    return {
        "base_price": base_price,
        "ulez_zone": ulez_zone,
        "ulez_surcharge": ulez_surcharge,
        "parts_estimate": parts_estimate,
        "calculated_price": calculated,
        "final_price": calculated,          # negotiation node may reduce this
        "floor_price": float(job_cfg["floor_price"]),
    }
