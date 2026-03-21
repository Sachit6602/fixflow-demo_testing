"""
Output Guard — the ONLY node that adds AI messages to state.messages.

All other nodes update state fields only. This node reads those fields and
composes the customer-facing response, stripping all internal data
(cost price, margin, engineer names, capacity data, floor price).

Also generates the quote reference and sets quote_issued when applicable.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict

from langchain_core.messages import AIMessage

from app.config import load_business_config
from app.state import QuoteState


def _quote_ref() -> str:
    timestamp = datetime.now().strftime("%Y%m%d")
    suffix = str(uuid.uuid4())[:6].upper()
    return f"FX-{timestamp}-{suffix}"


def _format_slots(slots: list) -> str:
    if not slots:
        return "  No slots available — please call us directly."
    lines = []
    for i, slot in enumerate(slots[:3], 1):
        lines.append(f"  {i}. {slot['date']}  {slot['time']}")
    return "\n".join(lines)


def _build_pricing_breakdown(state: QuoteState, config: dict) -> str:
    lines = []
    multiplier = state.get("urgency_multiplier", 1.0)
    ulez_surcharge = state.get("ulez_surcharge", 0.0)
    discount_pct = state.get("discount_pct", 0.0)
    urgency_tier = state.get("urgency_tier", "next_day")
    ulez_zone = state.get("ulez_zone", "outside")

    if multiplier > 1.0:
        tier_label = config["urgency_tiers"].get(urgency_tier, {}).get("label", urgency_tier)
        lines.append(f"  • {tier_label} surcharge (×{multiplier})")
    if ulez_surcharge > 0:
        zone_label = config["ulez_zones"].get(ulez_zone, {}).get("label", "")
        lines.append(f"  • ULEZ surcharge ({zone_label}): +£{ulez_surcharge:.2f}")
    if discount_pct > 0:
        customer_type = state.get("customer_type", "new")
        lines.append(f"  • {'Returning' if customer_type == 'returning' else 'New'} customer discount: −{discount_pct:.1f}%")

    return "\n".join(lines)


def output_guard_node(state: QuoteState) -> Dict[str, Any]:
    """
    Composes the final customer-facing message for this turn.
    Only adds an AI message when there is something new to say.
    """
    config = load_business_config()
    messages = state.get("messages", [])

    # ── Guard: don't double-respond ───────────────────────────────────────────
    # If the last message in state is already an AI message, this turn already
    # has a response (e.g. added by a previous node or a previous run). Skip.
    if messages and getattr(messages[-1], "type", None) == "ai":
        return {}

    # ── Safety hard stop ──────────────────────────────────────────────────────
    if state.get("safety_triggered"):
        if state.get("safety_type") == "gas_smell":
            text = config["gas_safety"]["hard_stop_message"]
        else:
            text = (
                "I'm unable to process that message. "
                f"For genuine emergencies please call us at {config['business']['phone']}."
            )
        return {
            "messages": [AIMessage(content=text)],
            "phase": "ended",
        }

    intent = state.get("intent")

    # ── Non-quote intent response ─────────────────────────────────────────────
    if intent in ("general_enquiry", "complaint", "emergency"):
        # intent_classifier stored its response in next_diagnostic_question
        carrier = state.get("next_diagnostic_question")
        if intent == "emergency":
            text = (
                "If you're in immediate danger, call **999**. "
                f"For emergency plumbing or boiler issues call us at **{config['business']['phone']}**."
            )
        else:
            text = carrier or (
                f"Thanks for getting in touch. Please call us at **{config['business']['phone']}** "
                "and our team will be happy to help."
            )
        return {
            "messages": [AIMessage(content=text)],
            "phase": "ended",
            "next_diagnostic_question": None,
        }

    # ── Out-of-scope ──────────────────────────────────────────────────────────
    if not state.get("in_scope", True) and state.get("job_type"):
        carrier = state.get("next_diagnostic_question")
        text = carrier or (
            f"We currently service **{', '.join(config['supported_brands'])}** boilers "
            "in London. If you have one of those brands, I'm happy to help — "
            "otherwise I'd recommend contacting a specialist for your make and model."
        )
        return {
            "messages": [AIMessage(content=text)],
            "phase": "ended",
            "next_diagnostic_question": None,
        }

    # ── Diagnostic question ───────────────────────────────────────────────────
    next_q = state.get("next_diagnostic_question")
    if not state.get("diagnostic_complete") and next_q:
        return {
            "messages": [AIMessage(content=next_q)],
            "phase": "diagnosis",
            "next_diagnostic_question": None,
        }

    # ── Escalation / hard block ───────────────────────────────────────────────
    if state.get("escalation_flag") or state.get("authority_level") == "hard_block":
        reason = state.get("escalation_reason") or "the complexity of this job"
        phone = config["business"]["phone"]
        text = (
            f"Based on what you've described, this job requires a specialist assessment — "
            f"{reason}. This falls outside our instant quote system. "
            f"A specialist will contact you within 2 hours to arrange a survey. "
            f"You can also reach us directly at **{phone}**."
        )
        return {
            "messages": [AIMessage(content=text)],
            "phase": "escalated",
        }

    # ── Negotiation response (already composed by negotiation node) ───────────
    if state.get("negotiation_round", 0) > 0 and next_q:
        return {
            "messages": [AIMessage(content=next_q)],
            "phase": "negotiating",
            "next_diagnostic_question": None,
        }

    # ── Self-help (offer DIY steps before quoting, when job supports it) ─────
    # Only offered once. On the next turn self_help_offered=True, we skip
    # straight to the quote.
    job_type = state.get("job_type")
    if (
        job_type
        and not state.get("self_help_offered")
        and not state.get("quote_issued")
        and state.get("calculated_price") is not None
    ):
        job_cfg = config["supported_job_types"].get(job_type, {})
        sh = job_cfg.get("self_help")
        if sh:
            steps_text = "\n".join(f"  {i}. {s}" for i, s in enumerate(sh["steps"], 1))
            text = (
                f"**{sh['title']}**\n\n"
                f"{sh['intro']}\n\n"
                f"**Steps:**\n{steps_text}\n\n"
                f"⚠️ {sh['warning']}\n\n"
                f"{sh['followup']}"
            )
            return {
                "messages": [AIMessage(content=text)],
                "phase": "self_help",
                "self_help_offered": True,
            }

    # ── Quote response ────────────────────────────────────────────────────────
    final_price = state.get("final_price") or state.get("calculated_price")
    if final_price is None:
        # Not enough state to produce a quote yet — no-op
        return {}

    job_label = (state.get("job_type") or "").replace("_", " ").title()
    confidence = state.get("confidence_level", "medium")
    authority = state.get("authority_level", "auto_confirm")
    slots = state.get("availability_slots", [])
    breakdown = _build_pricing_breakdown(state, config)
    price_note = " *(estimated — exact price confirmed on-site)*" if confidence != "high" else ""
    ref = state.get("quote_reference") or _quote_ref()

    if authority == "auto_confirm":
        text = (
            f"**Quote — {job_label}**\n\n"
            f"Price: **£{final_price:.2f}**{price_note}\n"
            + (f"\nPricing breakdown:\n{breakdown}\n" if breakdown else "")
            + f"\nAvailable slots:\n{_format_slots(slots)}\n\n"
            f"Quote reference: `{ref}`\n"
            f"Valid for: 24 hours\n\n"
            "Reply with your preferred slot number to confirm your appointment."
        )
    elif authority == "human_review":
        text = (
            f"**Quote — {job_label}**\n\n"
            f"Estimated price: **£{final_price:.2f}**{price_note}\n"
            + (f"\nPricing breakdown:\n{breakdown}\n" if breakdown else "")
            + "\nThis quote requires review by our team before it can be confirmed. "
            "A specialist will follow up within 2 hours.\n\n"
            f"Quote reference: `{ref}`"
        )
    else:
        # Should have been caught by escalation above, but handle defensively
        phone = config["business"]["phone"]
        text = (
            f"This job requires a specialist assessment. "
            f"Please call us at **{phone}** to arrange a survey."
        )

    return {
        "messages": [AIMessage(content=text)],
        "quote_reference": ref,
        "quote_issued": True,
        "quote_validity_hours": 24,
        "phase": "quoting",
        "next_diagnostic_question": None,
    }
