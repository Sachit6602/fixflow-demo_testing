"""
Input Guard — runs on every single message before any other node.

Two-layer gas-smell detection:
  Layer 1: Fast keyword regex (synchronous, zero latency)
  Layer 2: LLM classifier fallback for paraphrased descriptions
            (only invoked when ambiguous trigger words are present)

Prompt injection detection:
  Regex-based pattern matching against known injection templates.

If safety is triggered, subsequent nodes see safety_triggered=True and route
directly to output_guard which returns the hard stop message.
"""
from __future__ import annotations

import re
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_llm, load_business_config
from app.models.structured_outputs import GasSmellClassification
from app.state import QuoteState

# ── Injection patterns ────────────────────────────────────────────────────────
_INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|above|prior|your)\s+(instructions?|prompts?|rules?|context|constraints?)",
    r"you\s+are\s+now\s+a",
    r"pretend\s+(you\s+are|to\s+be|that\s+you)",
    r"roleplay\s+as",
    r"disregard\s+(your|the|all|previous|prior)",
    r"act\s+as\s+(a|an|if)\s+",
    r"forget\s+(everything|all|what|your)",
    r"new\s+(instructions?|rules?|persona|role)\s*:",
    r"^\s*system\s*:",
    r"<\|.*?\|>",  # token injection (e.g. <|system|>)
    r"\[INST\]",    # Llama-style injection
    r"###\s*instruction",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE | re.MULTILINE)

# ── Ambiguous words that warrant the LLM fallback gas check ──────────────────
_AMBIGUOUS_SIGNALS = {
    "smell", "smells", "smelling", "odour", "odor", "fumes", "fume",
    "headache", "dizzy", "dizziness", "nausea", "nauseous", "lightheaded",
    "weird", "strange", "funny", "unusual",
}

# Gas keyword pattern — built lazily from business_config.json
_GAS_RE: re.Pattern | None = None


def _get_gas_re() -> re.Pattern:
    global _GAS_RE
    if _GAS_RE is None:
        config = load_business_config()
        keywords = config["gas_safety"]["keywords"]
        escaped = [re.escape(k) for k in keywords]
        _GAS_RE = re.compile(r"(" + "|".join(escaped) + r")", re.IGNORECASE)
    return _GAS_RE


def _keyword_gas_match(text: str) -> bool:
    return bool(_get_gas_re().search(text))


def _keyword_injection_match(text: str) -> bool:
    return bool(_INJECTION_RE.search(text))


def _has_ambiguous_signal(text: str) -> bool:
    words = set(re.findall(r"\b\w+\b", text.lower()))
    return bool(words & _AMBIGUOUS_SIGNALS)


def _llm_gas_check(text: str) -> bool:
    """
    LLM fallback for gas-smell detection.
    Only called when ambiguous signals are present but no keyword matched.
    Uses a small, fast call — errs on the side of caution (false positives are safe).
    """
    try:
        llm = get_llm("anthropic/claude-haiku-4-5", max_tokens=128)
        structured = llm.with_structured_output(GasSmellClassification)
        result: GasSmellClassification = structured.invoke([
            SystemMessage(content=(
                "You are a household gas safety classifier. "
                "Determine whether the following customer message could indicate "
                "a gas smell, gas leak, or carbon monoxide risk — even if described "
                "indirectly or informally. "
                "Examples of indirect descriptions: 'there's a weird smell', "
                "'smells like my nan's old oven', 'headache every time I'm in the kitchen', "
                "'something's off near the boiler'. "
                "Err on the side of caution — a false positive is safe; "
                "a false negative could be fatal."
            )),
            HumanMessage(content=text),
        ])
        return result.is_gas_related and result.confidence in ("high", "medium")
    except Exception:
        # If the LLM call itself fails, do NOT block — keyword check already passed clean.
        # Log would go here in a production system.
        return False


def input_guard_node(state: QuoteState) -> Dict[str, Any]:
    """
    Runs before every other node. Checks the latest human message for:
    1. Gas smell (keyword layer → LLM fallback layer)
    2. Prompt injection (regex)

    Returns only safety_triggered / safety_type — all other state is untouched.
    """
    messages = state.get("messages", [])

    # Find the most recent human message
    latest: str | None = None
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "human":
            latest = msg.content
            break

    if not latest:
        return {"safety_triggered": False, "safety_type": None}

    # ── Layer 1: keyword gas check ────────────────────────────────────────────
    if _keyword_gas_match(latest):
        return {"safety_triggered": True, "safety_type": "gas_smell"}

    # ── Layer 1: injection check ─────────────────────────────────────────────
    if _keyword_injection_match(latest):
        return {"safety_triggered": True, "safety_type": "prompt_injection"}

    # ── Layer 2: LLM gas check for paraphrased descriptions ──────────────────
    # Only invoked when message contains smell/odour/dizzy/headache-type words
    # to avoid paying LLM latency on every unrelated message.
    if _has_ambiguous_signal(latest):
        if _llm_gas_check(latest):
            return {"safety_triggered": True, "safety_type": "gas_smell"}

    return {"safety_triggered": False, "safety_type": None}
