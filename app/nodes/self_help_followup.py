"""
Self-Help Followup Node — runs when phase="self_help" (after DIY steps have been shown).

Detects whether the customer's response indicates the self-help steps worked or not:

  resolved      → thanks them, ends the conversation (no callout needed)
  not_resolved  → offers a reduced diagnostic visit quote — a Gas Safe engineer
                  attends to diagnose and can repair on the spot. The visit fee
                  is credited towards any repair done on the same visit.
  unclear       → asks a clarifying question: "did those steps help?"

Design:
- Does NOT add AI messages to state directly — sets next_diagnostic_question as carrier
- output_guard delivers the message
- For diagnostic visit quote: reuses availability_slots already in state
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict

from langchain_core.messages import SystemMessage

from app.config import get_llm, load_business_config
from app.models.structured_outputs import SelfHelpOutcomeResult
from app.state import QuoteState
from app.utils.pii import get_safe_messages

_SYSTEM = """\
You are assessing a customer's reply after they were given DIY self-help steps \
for a boiler or plumbing issue.

Your only task is to classify their latest message into one of three outcomes:

  resolved     — the customer says the steps fixed the problem
                 Signals: 'yes it worked', 'sorted', 'it's working now', 'all good',
                 'fixed', 'boiler back on', 'pressure is back', 'thanks'.

  not_resolved — the customer says the issue is still present
                 Signals: 'didn't work', 'still showing error', 'no change',
                 'still broken', 'still the same', 'it hasn't helped', 'same problem'.

  unclear      — anything else: they haven't replied yet, are asking another
                 question, or the message is ambiguous.

Classify based ONLY on the most recent customer message.
"""


def _quote_ref() -> str:
    timestamp = datetime.now().strftime("%Y%m%d")
    suffix = str(uuid.uuid4())[:6].upper()
    return f"FX-{timestamp}-{suffix}"


def _format_slots(slots: list) -> str:
    if not slots:
        return "  No slots currently available — please call us directly."
    lines = []
    for i, slot in enumerate(slots[:3], 1):
        lines.append(f"  {i}. {slot['date']}  {slot['time']}")
    return "\n".join(lines)


def self_help_followup_node(state: QuoteState) -> Dict[str, Any]:
    llm = get_llm()
    structured = llm.with_structured_output(SelfHelpOutcomeResult)
    config = load_business_config()

    try:
        result: SelfHelpOutcomeResult = structured.invoke([
            SystemMessage(content=_SYSTEM),
            *get_safe_messages(state),
        ])
    except Exception as e:
        return {
            "error_state": f"self_help_followup: {e}",
            "retry_count": state.get("retry_count", 0) + 1,
            "next_diagnostic_question": (
                "Did those steps help? Let me know if the issue is resolved "
                "or if you're still seeing the problem."
            ),
        }

    # ── Resolved ─────────────────────────────────────────────────────────────
    if result.outcome == "resolved":
        return {
            "next_diagnostic_question": (
                "That's great news — glad you got it sorted! 🎉\n\n"
                "No engineer needed and no call-out charge. "
                "If the issue comes back (or if the pressure keeps dropping), "
                "just start a new chat and we'll get you booked in straight away. "
                "Have a great day!"
            ),
            "phase": "ended",
        }

    # ── Not resolved — ask for postcode first, then offer diagnostic visit ───────
    if result.outcome == "not_resolved":
        if not state.get("postcode"):
            # Postcode needed to calculate ULEZ — ask for it and defer the quote.
            return {
                "next_diagnostic_question": (
                    "No problem — before I put together your engineer visit quote, "
                    "could you share your postcode? (e.g. E14, SW1A, NW3) "
                    "We use it to check whether a ULEZ surcharge applies."
                ),
                "phase": "awaiting_postcode",
                "pending_self_help_quote": True,
            }
        # Postcode already known — build diagnostic visit quote now.
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
            breakdown_lines.append(f"  • ULEZ surcharge ({zone_label}): +£{ulez_surcharge:.2f}")
        breakdown = ("\n\nPricing breakdown:\n" + "\n".join(breakdown_lines)) if breakdown_lines else ""

        carrier = (
            f"No problem — let's get an engineer out to you.\n\n"
            f"**Diagnostic Visit Quote**\n\n"
            f"A Gas Safe registered engineer will attend to fully diagnose the issue "
            f"and advise on next steps.\n\n"
            f"Visit fee: **£{visit_price:.2f}**{breakdown}\n\n"
            f"✅ *{visit_cfg['redeemable_note']}*\n\n"
            f"Available slots:\n{_format_slots(slots)}\n\n"
            f"Quote reference: `{ref}`\n"
            f"Valid for: 24 hours\n\n"
            f"Reply with your preferred slot number to confirm."
        )
        return {
            "next_diagnostic_question": carrier,
            "calculated_price": visit_price,
            "final_price": visit_price,
            "floor_price": float(visit_cfg["floor_price"]),
            "quote_reference": ref,
            "quote_issued": True,
            "quote_validity_hours": 24,
            "phase": "quoting",
        }

    # ── Unclear — ask a clarifying question ──────────────────────────────────
    return {
        "next_diagnostic_question": (
            "Just checking in — did those steps help fix the issue? "
            "Reply **'yes, it's working'** if you're all sorted, or **'no, still broken'** "
            "if you'd like us to send an engineer."
        ),
    }
