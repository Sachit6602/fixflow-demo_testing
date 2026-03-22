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
        lines.append(f"  {i}. {slot['date']}: {slot['time']}")
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
    elif 0 < multiplier < 1.0:
        tier_label = config["urgency_tiers"].get(urgency_tier, {}).get("label", urgency_tier)
        saving_pct = round((1.0 - multiplier) * 100)
        lines.append(f"  • {tier_label} (−{saving_pct}% off standard rate)")
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

    # ── Guard: don't double-respond within a single invocation ───────────────
    # With phase-based routing, the previous AI message in state belongs to a
    # prior turn. We only skip if the LAST message is already AI (meaning
    # another node in this same invocation already added a response).
    last_is_human = messages and getattr(messages[-1], "type", None) == "human"
    if not last_is_human:
        return {}

    # ── /end command — goodbye ────────────────────────────────────────────────
    if state.get("phase") == "ended":
        text = (
            "Thanks for using FixFlow! If you need help again, just start a new conversation. "
            f"For urgent issues, call us anytime at **{config['business']['phone']}**."
        )
        return {
            "messages": [AIMessage(content=text)],
            "phase": "ended",
        }

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

    # ── Greeting — respond and stay in intake ─────────────────────────────────
    if intent == "greeting":
        customer_name = state.get("customer_name", "")
        name_part = f", {customer_name}" if customer_name and customer_name != "Customer" else ""
        customer_type = state.get("customer_type", "new")
        if customer_type == "returning":
            text = (
                f"Welcome back{name_part}! "
                "How can I help you today?"
            )
        else:
            text = (
                f"Hey there{name_part}! I'm FixFlow — your 24/7 plumbing and boiler assistant. "
                "How can I help you today?"
            )
        return {
            "messages": [AIMessage(content=text)],
            "phase": "intake",
            "intent": None,
            "next_diagnostic_question": None,
        }

    # ── Farewell — customer is done ─────────────────────────────────────────────
    if intent == "farewell":
        customer_name = state.get("customer_name", "")
        name_part = f", {customer_name}" if customer_name and customer_name != "Customer" else ""
        text = (
            f"Thanks for using FixFlow{name_part}! "
            f"If you ever need help again, just start a new conversation. "
            f"For urgent issues, call us anytime at **{config['business']['phone']}**. "
            "Have a great day!"
        )
        return {
            "messages": [AIMessage(content=text)],
            "phase": "ended",
        }

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
        # Stay alive — reset to intake so next message gets re-classified
        return {
            "messages": [AIMessage(content=text)],
            "phase": "intake",
            "intent": None,
            "next_diagnostic_question": None,
        }

    # ── Out-of-scope ──────────────────────────────────────────────────────────
    if not state.get("in_scope", True):
        carrier = state.get("next_diagnostic_question")
        text = carrier or (
            f"We currently service **{', '.join(config['supported_brands'])}** boilers "
            "in London. If you have one of those brands, I'm happy to help — "
            "otherwise I'd recommend contacting a specialist for your make and model."
        )
        text += "\n\nIs there anything else I can help you with?"
        # Reset all diagnostic and classification state so the customer can
        # start a completely fresh request in the same session.
        # Recovery flow: phase="intake" → next turn routes to intent_classifier
        # via _route_input_guard → re-classifies → new diagnostic cycle.
        return {
            "messages": [AIMessage(content=text)],
            "phase": "intake",
            "intent": None,
            "in_scope": True,
            "diagnostic_complete": False,
            "boiler_brand": None,
            "job_type": None,
            "confidence_level": None,
            "symptoms": [],
            "diagnostic_questions_asked": 0,
            "next_diagnostic_question": None,
            "escalation_flag": False,
            "escalation_reason": None,
            "calculated_price": None,
            "final_price": None,
            "base_price": None,
            "quote_issued": False,
            "self_help_offered": False,
            "pending_self_help_quote": False,
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

    # ── Awaiting postcode — deliver the postcode request ─────────────────────
    # Fires when self_help_followup (or another node) sets phase to
    # awaiting_postcode and provides a carrier message. Explicit check avoids
    # relying on diagnostic_complete being True from an earlier turn.
    if state.get("phase") == "awaiting_postcode" and next_q:
        return {
            "messages": [AIMessage(content=next_q)],
            "phase": "awaiting_postcode",
            "next_diagnostic_question": None,
        }

    # ── Negotiation / booking / self-help carrier ───────────────────────────────
    # The carrier fires whenever any post-diagnostic node (negotiation, etc.)
    # sets next_diagnostic_question to a composed message ready for delivery.
    # Resets intent so the next turn re-classifies if phase loops back to intake.
    if state.get("diagnostic_complete") and next_q:
        return {
            "messages": [AIMessage(content=next_q)],
            "phase": state.get("phase", "quoting"),
            "next_diagnostic_question": None,
            "intent": None,
        }

    # ── Already booked ─────────────────────────────────────────────────────
    # After the booking confirmation has been shown, respond to any follow-up
    # messages without re-quoting.
    if state.get("booking_confirmed"):
        phone = config["business"]["phone"]
        text = (
            "Your booking is all set — we'll see you at the scheduled time! "
            f"If you need to make any changes, please call us at **{phone}**. "
            "Is there anything else I can help you with?"
        )
        return {
            "messages": [AIMessage(content=text)],
            "phase": "intake",
            "intent": None,
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

    # ── Postcode required before quote ────────────────────────────────────────
    # Fires only when we are about to show the quote but don't have a postcode.
    # Self-help steps (if applicable) have already been shown by this point,
    # so this block naturally sits at the "imminent quote" position.
    if state.get("calculated_price") is not None and not state.get("postcode"):
        return {
            "messages": [AIMessage(content=(
                "One quick thing before your quote — what's your postcode? "
                "(e.g. SW1A, E14, NW3). We use it to check whether a ULEZ "
                "surcharge applies to your area."
            ))],
            "phase": "awaiting_postcode",
        }
    # ── Pending diagnostic visit quote (self-help failed → postcode just captured) ─
    # self_help_followup deferred the quote here when there was no postcode.
    # postcode_capture → pricing → negotiation → authority_check has now run,
    # so ulez_surcharge is correct and we can build the visit quote.
    if state.get("pending_self_help_quote") and state.get("postcode"):
        visit_cfg = config["self_help_diagnostic_visit"]
        base_price = float(visit_cfg["base_price"])
        ulez_surcharge = state.get("ulez_surcharge", 0.0)
        visit_price = base_price + ulez_surcharge
        ref = _quote_ref()
        slots = state.get("availability_slots", [])
        breakdown_lines = []
        if ulez_surcharge > 0:
            ulez_zone = state.get("ulez_zone", "outside")
            zone_label = config["ulez_zones"].get(ulez_zone, {}).get("label", "")
            breakdown_lines.append(f"  \u2022 ULEZ surcharge ({zone_label}): +\u00a3{ulez_surcharge:.2f}")
        breakdown = ("\n\nPricing breakdown:\n" + "\n".join(breakdown_lines)) if breakdown_lines else ""
        text = (
            f"No problem — let's get an engineer out to you.\n\n"
            f"**Diagnostic Visit Quote**\n\n"
            f"A Gas Safe registered engineer will attend to fully diagnose the issue "
            f"and advise on next steps.\n\n"
            f"Visit fee: **\u00a3{visit_price:.2f}**{breakdown}\n\n"
            f"\u2705 *{visit_cfg['redeemable_note']}*\n\n"
            f"Available slots:\n{_format_slots(slots)}\n\n"
            f"Quote reference: `{ref}`\n"
            f"Valid for: 24 hours\n\n"
            f"Reply with your preferred slot number to confirm."
        )
        return {
            "messages": [AIMessage(content=text)],
            "calculated_price": visit_price,
            "final_price": visit_price,
            "floor_price": float(visit_cfg["floor_price"]),
            "quote_reference": ref,
            "quote_issued": True,
            "quote_validity_hours": 24,
            "phase": "quoting",
            "pending_self_help_quote": False,
            "next_diagnostic_question": None,
        }

    # ── Post-quote (quote already sent, no new negotiation response) ─────────
    if state.get("quote_issued") and not next_q:
        text = (
            "Is there anything else I can help you with? "
            "I can quote for a different issue or answer any questions."
        )
        return {
            "messages": [AIMessage(content=text)],
            "phase": "intake",
            "intent": None,
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
