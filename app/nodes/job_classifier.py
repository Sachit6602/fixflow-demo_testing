"""
Job Classifier — runs once (passes through if job_type already set).

Validates the request against business_config.json scope, classifies job type,
and flags escalations (boiler replacement or high-confidence old-boiler scenario).

Scope validation is done here in node logic, NOT via LLM prompt instruction,
to prevent hallucinated out-of-scope responses.
"""
from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_llm, load_business_config
from app.models.structured_outputs import JobClassification
from app.state import QuoteState
from app.utils.pii import get_safe_messages

_SYSTEM = """\
You are FixFlow's job classifier for a London plumbing and boiler service.

Supported boiler brands: {brands}
Supported job types (use these exact keys): {job_type_keys}
Coverage: London postcodes only

Your task:
1. Classify the symptoms into one of the supported job types.
2. Assess confidence (high / medium / low) based on symptom detail.
3. Set in_scope=False if: the brand is not in supported_brands, the job type \
   cannot be matched, or the location is clearly outside London.
4. Set escalation_flag=True for boiler_replacement or if \
   the boiler is 15+ years old with multiple failure symptoms.

Confidence levels:
- high: 4+ clear specific symptoms clearly pointing to one job type
- medium: 2–3 symptoms with some ambiguity
- low: 1 or fewer symptoms, or significant ambiguity between job types

When in_scope=False, write a helpful out_of_scope_message that states what we \
do support and, where possible, suggests an alternative.
"""


def job_classifier_node(state: QuoteState) -> Dict[str, Any]:
    # Pass through — already classified
    if state.get("job_type") is not None:
        return {}

    config = load_business_config()
    brands = ", ".join(config["supported_brands"])
    job_type_keys = ", ".join(config["supported_job_types"].keys())

    symptoms = state.get("symptoms", [])

    llm = get_llm()
    structured = llm.with_structured_output(JobClassification)

    try:
        result: JobClassification = structured.invoke([
            SystemMessage(content=_SYSTEM.format(brands=brands, job_type_keys=job_type_keys)),
            HumanMessage(content=f"Symptoms extracted: {', '.join(symptoms) or 'none provided'}"),
            *get_safe_messages(state),
        ])

        updates: Dict[str, Any] = {
            "job_type": result.job_type,
            "confidence_level": result.confidence_level,
            "in_scope": result.in_scope,
            "escalation_flag": result.escalation_flag,
            "escalation_reason": result.escalation_reason,
        }

        # Set floor price from config for this job type
        job_cfg = config["supported_job_types"].get(result.job_type, {})
        if job_cfg:
            updates["floor_price"] = float(job_cfg["floor_price"])

        # Carry the out-of-scope message through to output_guard
        if not result.in_scope and result.out_of_scope_message:
            updates["next_diagnostic_question"] = result.out_of_scope_message  # reused as a carrier field

        return updates

    except Exception as e:
        return {
            "job_type": "boiler_minor_repair",
            "confidence_level": "low",
            "in_scope": True,
            "escalation_flag": False,
            "floor_price": float(config["supported_job_types"]["boiler_minor_repair"]["floor_price"]),
            "error_state": f"job_classifier: {e}",
            "retry_count": state.get("retry_count", 0) + 1,
        }
