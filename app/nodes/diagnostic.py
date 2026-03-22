"""
Diagnostic Node — runs once per turn while diagnostic is incomplete.

Extracts symptoms from the customer's messages and asks follow-up questions.
Maximum 5 questions total; terminates and proceeds after 5 Q&A pairs regardless
of confidence level (resolves the FR9 / FR11 contradiction in the original PRD).

Design:
- Does NOT add AI messages directly to state.messages
- Sets next_diagnostic_question for output_guard to deliver
- Accumulates symptoms across turns (de-duplicated)
"""
from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import SystemMessage

from app.config import get_llm, load_business_config
from app.models.structured_outputs import DiagnosticResult
from app.state import QuoteState
from app.utils.pii import get_safe_messages

MAX_QUESTIONS = 5

_SYSTEM = """\
You are FixFlow's diagnostic specialist for a London plumbing and boiler service.

Supported boiler brands: {supported_brands}
Brand status: {brand_status}

Questions asked so far: {questions_asked} / {max_questions}
Questions remaining: {questions_remaining}
Symptoms already extracted: {symptoms}

RULES — follow in strict priority order:

1. BRAND GATE (highest priority):
   - If brand_status is "unknown", extract the boiler make from the customer's message \
into brand_extracted.
   - If no brand is mentioned yet, set next_question to ask: "What make is your boiler?" \
and nothing else. Do NOT ask about symptoms yet.
   - Once you have a brand name, set brand_extracted to it regardless of whether it is \
supported — the system will validate it.

2. SYMPTOM COLLECTION (only when brand is already confirmed):
   - Ask exactly ONE targeted follow-up per turn. No compound questions. No bullet lists.
   - Focus on: error code, hot water affected, boiler pressure, boiler age, symptom \
duration, urgency.
   - If the customer says they don't know or can't check (e.g. "can't see", "not sure", \
"I don't know"), do NOT treat that as a symptom or complete the diagnosis. Instead, \
skip that question and ask the next relevant one. Only set diagnostic_complete=True \
when you have at least 2 concrete symptoms, or when questions_remaining is 0.

3. POSTCODE: Do NOT ask for it — collected separately. If the customer volunteers \
it, capture in postcode_extracted.
"""


def diagnostic_node(state: QuoteState) -> Dict[str, Any]:
    # Pass through — already complete
    if state.get("diagnostic_complete"):
        return {}

    config = load_business_config()
    supported_brands: List[str] = config["supported_brands"]
    supported_lower = {b.lower(): b for b in supported_brands}

    boiler_brand = state.get("boiler_brand")  # None until confirmed
    questions_asked = state.get("diagnostic_questions_asked", 0)
    questions_remaining = MAX_QUESTIONS - questions_asked
    existing_symptoms: List[str] = state.get("symptoms", [])

    brand_status = f"confirmed ({boiler_brand})" if boiler_brand else "unknown — ask for it first"

    llm = get_llm()
    structured = llm.with_structured_output(DiagnosticResult)

    try:
        result: DiagnosticResult = structured.invoke([
            SystemMessage(content=_SYSTEM.format(
                supported_brands=", ".join(supported_brands),
                brand_status=brand_status,
                questions_asked=questions_asked,
                max_questions=MAX_QUESTIONS,
                questions_remaining=questions_remaining,
                symptoms=", ".join(existing_symptoms) if existing_symptoms else "none yet",
            )),
            *get_safe_messages(state),
        ])

        updates: Dict[str, Any] = {}

        # ── Brand gate — runs only until brand is confirmed ───────────────────
        if result.brand_extracted and not boiler_brand:
            raw_brand = result.brand_extracted.strip()
            if raw_brand.lower() in supported_lower:
                # Supported — normalise to configured casing and continue
                updates["boiler_brand"] = supported_lower[raw_brand.lower()]
            else:
                # Unsupported brand — short-circuit, no further questions needed
                brands_str = ", ".join(supported_brands)
                return {
                    "in_scope": False,
                    "diagnostic_complete": True,
                    "next_diagnostic_question": (
                        f"I'm sorry — we currently only service {brands_str} boilers. "
                        f"Unfortunately we're not able to quote for {raw_brand} boilers. "
                        "I'd recommend contacting the manufacturer's approved service "
                        "network or a local engineer who covers your make."
                    ),
                }

        # ── Accumulate symptoms ───────────────────────────────────────────────
        merged = list(dict.fromkeys(existing_symptoms + result.symptoms_extracted))
        updates["symptoms"] = merged

        if result.postcode_extracted:
            updates["postcode"] = result.postcode_extracted

        # Force completion if at question limit — but NEVER complete without a brand
        has_brand = bool(boiler_brand or updates.get("boiler_brand"))
        hit_limit = questions_remaining <= 0
        is_complete = (result.diagnostic_complete or hit_limit) and has_brand
        updates["diagnostic_complete"] = is_complete

        if not is_complete:
            # If LLM didn't provide a question, supply the brand gate question
            question = result.next_question
            if not question:
                if not has_brand:
                    question = "What make is your boiler? We service Vaillant, Baxi, Ideal, and LG."
                else:
                    question = "Could you describe what's happening with your boiler or plumbing?"
            # Only count symptom questions toward the limit, not brand gate
            if has_brand:
                updates["diagnostic_questions_asked"] = questions_asked + 1
            updates["next_diagnostic_question"] = question
        elif is_complete and len(merged) < 2 and hit_limit:
            # Hit question limit without enough concrete symptoms —
            # offer a diagnostic visit instead of forcing a shaky quote.
            phone = config["business"]["phone"]
            visit_cfg = config["self_help_diagnostic_visit"]
            updates["next_diagnostic_question"] = (
                "I don't have quite enough detail to quote remotely, but no worries — "
                f"we can send a **Gas Safe registered engineer** for a diagnostic visit "
                f"at **£{visit_cfg['base_price']}**. "
                f"*{visit_cfg['redeemable_note']}*\n\n"
                "Would you like me to check available slots, or would you prefer to "
                f"call us directly at **{phone}**?"
            )
            # Mark as needing the diagnostic visit flow
            updates["pending_self_help_quote"] = True
        else:
            updates["next_diagnostic_question"] = None

        return updates

    except Exception as e:
        # On LLM failure: force completion with whatever symptoms we have so
        # the demo doesn't stall. The job classifier will handle low-confidence.
        return {
            "diagnostic_complete": True,
            "next_diagnostic_question": None,
            "error_state": f"diagnostic: {e}",
            "retry_count": state.get("retry_count", 0) + 1,
        }
