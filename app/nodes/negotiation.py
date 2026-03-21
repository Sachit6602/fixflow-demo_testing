"""
Negotiation Node — runs on every turn after pricing.

Detects price pushback in the latest customer message using the LLM structured
output. If pushback is detected, applies a discount up to the configured max for
the customer type. Floor price is enforced as a hard cap regardless of LLM output.

Returning customer status is SELF-DECLARED (customer says "I'm a returning
customer"). The system accepts this in good faith per business policy — there is
no auth or session history to verify it. This is clearly called out in the
business_config.json discounts.returning_customer_note field.

After negotiation_round reaches the configured max, no further discounts are
offered regardless of continued pushback.
"""
from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import SystemMessage

from app.config import get_llm, load_availability, load_business_config, resolve_slot_dates
from app.models.structured_outputs import NegotiationResult
from app.state import QuoteState
from app.utils.pii import get_safe_messages

_SYSTEM = """\
You are FixFlow's post-quote conversation handler for a London plumbing and boiler service.

Current quote:
  Job:               {job_type}
  Calculated price:  £{calculated_price:.2f}
  Floor price:       £{floor_price:.2f}  ← NEVER go below this
  Customer type:     {customer_type} (self-declared — accepted in good faith)
  Max discount:      {max_discount}%
  Negotiation round: {negotiation_round} (max: {max_rounds})
  Urgency applied:   {urgency_multiplier}×

Your PRIMARY job is to classify the customer's intent into exactly one of three categories:

1. BOOKING — set booking_intent=True
   The customer is accepting the quote and wants to secure an appointment.
   Signals: 'yes', 'book it', 'confirm', 'I'll take it', 'slot 1', 'option 2',
   'slot 2', 'let's go ahead', replying with just '1', '2', or '3'.
   If a slot number (1/2/3) is mentioned, set slot_selected to that number.

2. SELF-HELP QUERY — set self_help_query=True
   The customer is asking whether they can fix it themselves.
   Signals: 'can I fix it myself?', 'is this DIY?', 'how do I do it?',
   'can I do it myself?', 'what steps do I take?', 'can I just...'

3. PRICE PUSHBACK — set is_pushback=True
   The customer is objecting to the price or asking for a discount.
   Signals: 'too expensive', 'can you do better?', 'my other quote was cheaper',
   'can you match X?', 'that's a lot', 'discount?'.
   Only ONE of (booking_intent, self_help_query, reschedule_request, is_pushback) can be True.
   For reschedule, also set slot_date_preference to 'today' or 'tomorrow' if a date is mentioned.

If none of the above, set all four to False and return an empty response string.

Business rules for price pushback (NON-NEGOTIABLE):
1. NEVER offer a final price below £{floor_price:.2f}
2. Do NOT match competitor prices — explain our value instead
3. Maximum discount: {max_discount}% for this customer type
4. After round {max_rounds}, hold firm — no further discounts

Our value propositions (use in pushback responses):
{value_props}
"""


def negotiation_node(state: QuoteState) -> Dict[str, Any]:
    # Cannot negotiate without a price
    if state.get("calculated_price") is None:
        return {}

    config = load_business_config()
    neg_cfg = config["negotiation"]
    disc_cfg = config["discounts"]
    max_rounds = neg_cfg["max_negotiation_rounds"]

    customer_type = state.get("customer_type", "new")
    negotiation_round = state.get("negotiation_round", 0)
    calculated_price = state.get("calculated_price", 0.0)
    floor_price = state.get("floor_price", calculated_price * 0.8)
    existing_discount = state.get("discount_pct", 0.0)

    max_discount = (
        disc_cfg["returning_customer_max_pct"]
        if customer_type == "returning"
        else disc_cfg["new_customer_max_pct"]
    )
    value_props = "\n".join(f"  • {v}" for v in neg_cfg["value_propositions"])

    llm = get_llm()
    structured = llm.with_structured_output(NegotiationResult)

    try:
        result: NegotiationResult = structured.invoke([
            SystemMessage(content=_SYSTEM.format(
                job_type=(state.get("job_type") or "").replace("_", " ").title(),
                calculated_price=calculated_price,
                floor_price=floor_price,
                customer_type=customer_type,
                max_discount=max_discount,
                negotiation_round=negotiation_round,
                max_rounds=max_rounds,
                urgency_multiplier=state.get("urgency_multiplier", 1.0),
                value_props=value_props,
            )),
            *get_safe_messages(state),
        ])

        # ── Booking intent ───────────────────────────────────────────────────
        if result.booking_intent:
            slots = state.get("availability_slots", [])
            slot_num = result.slot_selected
            if slot_num and 1 <= slot_num <= len(slots):
                chosen = slots[slot_num - 1]
                slot_text = f"{chosen['date']} at {chosen['time']}"
            elif slots:
                slot_text = f"{slots[0]['date']} at {slots[0]['time']}"
            else:
                slot_text = "your preferred time"

            ref = state.get("quote_reference", "N/A")
            final = state.get("final_price") or state.get("calculated_price", 0.0)
            job_label = (state.get("job_type") or "").replace("_", " ").title()
            confirmation = (
                f"Your appointment is confirmed! 🎉\n\n"
                f"**Booking details:**\n"
                f"  \u2022 Job: {job_label}\n"
                f"  \u2022 Date/Time: {slot_text}\n"
                f"  \u2022 Price: \u00a3{final:.2f}\n"
                f"  \u2022 Reference: `{ref}`\n\n"
                f"Our engineer will call 30 minutes before arrival. "
                f"Is there anything else I can help you with?"
            )
            return {
                "next_diagnostic_question": confirmation,
                "booking_confirmed": True,
                "phase": "booked",
            }

        # ── Self-help re-query ───────────────────────────────────────────────
        if result.self_help_query:
            job_type = state.get("job_type")
            sh_text = None
            if job_type:
                sh = config["supported_job_types"].get(job_type, {}).get("self_help")
                if sh:
                    steps_text = "\n".join(f"  {i}. {s}" for i, s in enumerate(sh["steps"], 1))
                    sh_text = (
                        f"**{sh['title']}**\n\n"
                        f"{sh['intro']}\n\n"
                        f"**Steps:**\n{steps_text}\n\n"
                        f"\u26a0\ufe0f {sh['warning']}\n\n"
                        f"{sh['followup']}"
                    )
            return {
                "next_diagnostic_question": sh_text or (
                    "This job is best handled by a professional — DIY isn't "
                    "recommended for this type of repair. Would you like to confirm "
                    "your appointment instead?"
                ),
            }

        # ── Reschedule request ────────────────────────────────────────────────────
        if result.reschedule_request:
            import datetime
            availability_data = load_availability()
            pref = (result.slot_date_preference or "").lower()

            # Pick the tier that matches what the customer asked for.
            if pref == "today":
                tier = "same_day"
            elif pref == "tomorrow":
                tier = "next_day"
            else:
                # No preference — use whatever tier is already in state,
                # defaulting to next_day so we always show something useful.
                tier = state.get("urgency_tier") or "next_day"

            # Resolve date placeholders to human-readable dates.
            raw_slots = availability_data["slots"].get(tier, [])[:3]
            slots = resolve_slot_dates(raw_slots)

            slot_lines = "\n".join(
                f"  {i}. {s['date']}  {s['time']}"
                for i, s in enumerate(slots, 1)
            ) if slots else "  No slots available for that date — please call us."
            job_label = (state.get("job_type") or "").replace("_", " ").title()
            final = state.get("final_price") or state.get("calculated_price", 0.0)
            ref = state.get("quote_reference", "N/A")
            carrier = (
                f"Of course — here are the available slots for your "
                f"**{job_label}** visit:\n\n"
                f"{slot_lines}\n\n"
                f"Price: **\u00a3{final:.2f}** | Reference: `{ref}`\n\n"
                f"Reply with the slot number you'd prefer."
            )
            return {
                "next_diagnostic_question": carrier,
                "availability_slots": slots,
                "urgency_tier": tier,
                "booking_confirmed": False,
                "phase": "quoting",
            }

        # ── Cheaper slot request ──────────────────────────────────────────────────
        if result.cheaper_slot_request:
            import datetime
            availability_data = load_availability()
            wa_tier = "weekday_afternoon"
            wa_cfg = config["urgency_tiers"].get(wa_tier, {})
            wa_multiplier = float(wa_cfg.get("multiplier", 1.0))
            wa_label = wa_cfg.get("label", "Weekday afternoon")

            # Filter to actual weekday days before resolving dates
            today_dt = datetime.date.today()
            raw_all = availability_data["slots"].get(wa_tier, [])
            weekday_raw = []
            for s in raw_all:
                raw_date = s.get("date", "")
                if raw_date.startswith("day_"):
                    try:
                        n = int(raw_date.split("_", 1)[1])
                        if (today_dt + datetime.timedelta(days=n)).weekday() < 5:
                            weekday_raw.append(s)
                    except (ValueError, IndexError):
                        weekday_raw.append(s)
                else:
                    weekday_raw.append(s)

            slots = resolve_slot_dates(weekday_raw[:3])

            # Recalculate price with the cheaper multiplier
            base_price = float(state.get("base_price") or 0.0)
            ulez_surcharge = state.get("ulez_surcharge", 0.0)
            parts_estimate = state.get("parts_estimate", 0.0)
            new_price = round((base_price * wa_multiplier) + ulez_surcharge + parts_estimate, 2)
            floor = float(state.get("floor_price") or 0.0)
            new_price = max(new_price, floor)

            job_label = (state.get("job_type") or "").replace("_", " ").title()
            ref = state.get("quote_reference", "N/A")
            orig = state.get("calculated_price") or new_price
            saving = round(orig - new_price, 2)
            slot_lines = "\n".join(
                f"  {i}. {s['date']}  {s['time']}"
                for i, s in enumerate(slots, 1)
            ) if slots else "  No weekday afternoon slots available right now."
            saving_note = (
                f" (saving **£{saving:.2f}** vs. the standard rate)"
                if saving > 0 else ""
            )
            carrier = (
                f"Good news — our **{wa_label}** slots (Mon–Fri, 12pm–5pm) are "
                f"priced at **£{new_price:.2f}**{saving_note} for your **{job_label}**:\n\n"
                f"{slot_lines}\n\n"
                f"Quote reference: `{ref}`\n\n"
                f"Reply with your preferred slot number to confirm."
            )
            return {
                "next_diagnostic_question": carrier,
                "availability_slots": slots,
                "urgency_tier": wa_tier,
                "urgency_multiplier": wa_multiplier,
                "calculated_price": new_price,
                "final_price": new_price,
                "discount_pct": 0.0,
                "booking_confirmed": False,
                "phase": "quoting",
            }

        # Not pushback, booking, self-help, reschedule, or cheaper slot — pass through
        if not result.is_pushback:
            return {}

        updates: Dict[str, Any] = {
            "negotiation_round": negotiation_round + 1,
            "competitor_match_attempted": result.competitor_match_attempted,
        }

        if result.offer_discount and negotiation_round < max_rounds:
            # Guardrail: cap at configured max; never breach floor price
            safe_discount = min(result.discount_pct, max_discount)
            discounted = calculated_price * (1 - safe_discount / 100)
            if discounted < floor_price:
                # Recalculate to land exactly at floor
                safe_discount = round(((calculated_price - floor_price) / calculated_price) * 100, 2)
                discounted = floor_price

            updates["discount_pct"] = safe_discount
            updates["final_price"] = round(discounted, 2)

        # Store the negotiation response for output_guard
        updates["next_diagnostic_question"] = result.response  # reused as a carrier

        return updates

    except Exception as e:
        return {
            "error_state": f"negotiation: {e}",
            "retry_count": state.get("retry_count", 0) + 1,
        }
