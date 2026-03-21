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

from app.config import get_llm
from app.models.structured_outputs import DiagnosticResult
from app.state import QuoteState

MAX_QUESTIONS = 5

_SYSTEM = """\
You are FixFlow's diagnostic specialist. Your role is to extract symptoms from \
a customer's messages about their plumbing or boiler problem and ask targeted \
follow-up questions to gather enough information to classify the job.

Questions asked so far: {questions_asked} / {max_questions}
Questions remaining: {questions_remaining}
Symptoms already extracted: {symptoms}

Rules:
- Ask exactly ONE question per turn. No bullet lists. No compound questions.
- Focus on: error code, hot water affected, boiler pressure, boiler age, type and \
  duration of problem, urgency.
- If questions_remaining is 0, set diagnostic_complete=True regardless.
- If you have enough to classify the job (even at low confidence), set \
  diagnostic_complete=True.
- Extract symptoms from the customer's latest reply, even if partial.
"""


def diagnostic_node(state: QuoteState) -> Dict[str, Any]:
    # Pass through — already complete
    if state.get("diagnostic_complete"):
        return {}

    questions_asked = state.get("diagnostic_questions_asked", 0)
    questions_remaining = MAX_QUESTIONS - questions_asked
    existing_symptoms: List[str] = state.get("symptoms", [])

    llm = get_llm("anthropic/claude-sonnet-4-5")
    structured = llm.with_structured_output(DiagnosticResult)

    try:
        result: DiagnosticResult = structured.invoke([
            SystemMessage(content=_SYSTEM.format(
                questions_asked=questions_asked,
                max_questions=MAX_QUESTIONS,
                questions_remaining=questions_remaining,
                symptoms=", ".join(existing_symptoms) if existing_symptoms else "none yet",
            )),
            *state.get("messages", []),
        ])

        # Accumulate and de-duplicate symptoms
        merged = list(dict.fromkeys(existing_symptoms + result.symptoms_extracted))

        # Force completion if at limit
        is_complete = result.diagnostic_complete or questions_remaining == 0

        updates: Dict[str, Any] = {
            "symptoms": merged,
            "diagnostic_complete": is_complete,
        }

        if not is_complete and result.next_question:
            updates["diagnostic_questions_asked"] = questions_asked + 1
            updates["next_diagnostic_question"] = result.next_question
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
