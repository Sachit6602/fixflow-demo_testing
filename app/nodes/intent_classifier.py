"""
Intent Classifier — runs once per session (passes through if intent already set).

Classifies the customer's primary intent and extracts initial context:
  - customer_type (auto-detected via Luffa uid when available, self-declared as fallback)
  - postcode (if mentioned)

For non-quote intents, the LLM also drafts the customer-facing response,
which output_guard will use.
"""
from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import SystemMessage

from app.config import get_llm, load_business_config
from app.models.structured_outputs import IntentClassification
from app.state import QuoteState
from app.utils.pii import get_safe_messages

_SYSTEM = """\
You are FixFlow — an AI quoting agent for emergency plumbing and boiler services in London.

Services offered:
- Emergency plumbing repairs (leaks, burst pipes)
- Boiler servicing, repairs, and replacements

Supported boiler brands: {supported_brands}
Coverage area: London only (inner and outer London postcodes)

Your task:
1. Classify the customer's intent.
2. Note if the customer EXPLICITLY self-identifies as a returning customer.
3. Extract their postcode if explicitly mentioned.
4. ONLY for non-quote intents, write a brief response in non_quote_response.

CRITICAL CLASSIFICATION RULE:
Default to 'quote_request' for ANY of the following — even if vague:
  - Describing a problem ("my boiler isn't working", "no hot water", "pipe is leaking")
  - Asking about price or cost
  - Describing symptoms of any plumbing or boiler issue
  - Requesting a repair, service, or fix
  - Asking how much something costs
  - Any message that could plausibly be the start of a service request

Only use other intents when unambiguous:
  - general_enquiry: clearly asking a factual question ("what areas do you cover?", "what brands do you service?")
  - complaint: explicitly unhappy about a PAST job
  - emergency: life-threatening situation NOT related to gas (gas is handled separately)

When in doubt, choose quote_request.
"""


def intent_classifier_node(state: QuoteState) -> Dict[str, Any]:
    # Pass through — intent already classified in a previous turn
    if state.get("intent") is not None:
        return {}

    # No human message yet (e.g. during session seed) — don't call the LLM.
    # Default to quote_request; it will be confirmed on the first real message.
    messages = state.get("messages", [])
    has_human_message = any(getattr(m, "type", None) == "human" for m in messages)
    if not has_human_message:
        return {"intent": "quote_request"}

    config = load_business_config()
    brands = ", ".join(config["supported_brands"])

    llm = get_llm()
    structured = llm.with_structured_output(IntentClassification)

    try:
        result: IntentClassification = structured.invoke([
            SystemMessage(content=_SYSTEM.format(supported_brands=brands)),
            *get_safe_messages(state),
        ])

        # Only upgrade, never downgrade — uid-verified returning status takes priority
        if result.customer_type == "returning" or state.get("customer_type") == "returning":
            derived_type = "returning"
        else:
            derived_type = result.customer_type

        updates: Dict[str, Any] = {
            "intent": result.intent,
            "customer_type": derived_type,
        }
        # Store the non-quote response so output_guard can use it
        if result.non_quote_response:
            updates["next_diagnostic_question"] = result.non_quote_response  # reuse field as carrier

        return updates

    except Exception as e:
        # Safe default: assume quote request so the conversation continues
        return {
            "intent": "quote_request",
            "error_state": f"intent_classifier: {e}",
            "retry_count": state.get("retry_count", 0) + 1,
        }
