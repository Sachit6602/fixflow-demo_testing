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

from app.config import get_llm, load_business_config
from app.models.structured_outputs import NegotiationResult
from app.state import QuoteState

_SYSTEM = """\
You are FixFlow's negotiation handler for a London plumbing and boiler service.

Current quote:
  Job:               {job_type}
  Calculated price:  £{calculated_price:.2f}
  Floor price:       £{floor_price:.2f}  ← NEVER go below this
  Customer type:     {customer_type} (self-declared — accepted in good faith)
  Max discount:      {max_discount}%
  Negotiation round: {negotiation_round} (max: {max_rounds})
  Urgency applied:   {urgency_multiplier}×

Business rules (NON-NEGOTIABLE):
1. NEVER offer a final price below £{floor_price:.2f}
2. Do NOT match competitor prices — explain our value instead
3. Maximum discount: {max_discount}% for this customer type
4. After round {max_rounds}, hold firm — no further discounts
5. Always decline competitor price-matching politely but firmly

Our value propositions (use in responses):
{value_props}

Assess whether the customer's latest message is pushing back on price. If so,
determine the appropriate response (discount, hold firm, or decline match).
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

    llm = get_llm("anthropic/claude-sonnet-4-5")
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
            *state.get("messages", []),
        ])

        # Not a pushback message — pass through without changing prices
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
