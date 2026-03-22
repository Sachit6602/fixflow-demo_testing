"""
PII masking utilities — applied before passing conversation history to LLMs.

Once a customer's postcode (or other PII) has been extracted and stored in
structured state, subsequent LLM calls have no need to see the raw value.
Masking it replaces the actual data with a placeholder token so the model
only ever processes anonymised text.

Architecture principle: postcode → zone lookup is PURE CODE (get_ulez_zone in
config.py). The LLM never needs to process or determine postcode values. All
nodes that call an LLM must use get_safe_messages(state) instead of accessing
state["messages"] directly — this guarantees the raw postcode is stripped from
every message before it reaches a model, even if a customer mentioned it early
in the conversation before the postcode_capture node ran.
"""
from __future__ import annotations

import re
from copy import copy
from typing import TYPE_CHECKING, List

from langchain_core.messages import BaseMessage

if TYPE_CHECKING:
    from app.state import QuoteState

# Full UK postcode — e.g. "SW1A 2AA", "E1 7AB", "NW10 3QP", "EC1A1BB"
_POSTCODE_RE = re.compile(
    r"\b[A-Z]{1,2}[0-9][A-Z0-9]?\s*[0-9][A-Z]{2}\b",
    re.IGNORECASE,
)

# UK phone numbers — 11-digit starting 0, or international +44/0044 format
_PHONE_RE = re.compile(
    r"\b(?:\+44\s?|0044\s?)?0[1-9]\d{8,9}\b",
)


def mask_pii(text: str) -> str:
    """Replace postcodes and phone numbers in *text* with placeholder tokens."""
    text = _POSTCODE_RE.sub("[POSTCODE]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    return text


def mask_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """Return a new list of messages with PII replaced by placeholder tokens.

    Only string content is altered — message type, id, and metadata are
    preserved. The originals stored in state are never modified.
    """
    result = []
    for msg in messages:
        if isinstance(msg.content, str):
            masked = mask_pii(msg.content)
            if masked != msg.content:
                # Shallow-copy preserving the concrete message subclass
                new_msg = copy(msg)
                new_msg.content = masked
                result.append(new_msg)
                continue
        result.append(msg)
    return result


def get_safe_messages(state: "QuoteState") -> List[BaseMessage]:
    """Extract messages from state and apply PII masking in one call.

    Use this in every LLM-calling node instead of state.get("messages", []).
    Ensures postcodes, phone numbers, and other PII are scrubbed from the
    conversation history before any model processes it.
    """
    return mask_messages(state.get("messages", []))
