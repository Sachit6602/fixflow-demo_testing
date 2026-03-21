from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class QuoteState(TypedDict):
    # ── Conversation ────────────────────────────────────────────────────────────
    # add_messages reducer: every node that returns {"messages": [...]} appends
    # to this list rather than overwriting it. Only output_guard adds AI messages.
    messages: Annotated[List[BaseMessage], add_messages]
    session_id: str
    customer_name: str

    # ── Safety (re-evaluated by input_guard on every turn) ───────────────────
    safety_triggered: bool
    safety_type: Optional[str]          # "gas_smell" | "prompt_injection"

    # ── Intent (set once by intent_classifier, persists) ────────────────────
    intent: Optional[str]               # "quote_request" | "general_enquiry" | "complaint" | "emergency"

    # ── Phase (updated by nodes to drive routing) ───────────────────────────
    phase: str                          # "intake" | "diagnosis" | "quoting" | "negotiating" | "escalated" | "ended" | "awaiting_postcode" | "self_help" | "booked"

    # ── Diagnosis ───────────────────────────────────────────────────────────
    # Max 5 questions total; terminate after 5 Q&A pairs regardless.
    diagnostic_questions_asked: int     # incremented each time a question is sent
    symptoms: List[str]
    diagnostic_complete: bool
    # Set by diagnostic node; read by output_guard to send the next question.
    next_diagnostic_question: Optional[str]

    # ── Job Classification ───────────────────────────────────────────────────
    job_type: Optional[str]
    confidence_level: Optional[str]     # "high" | "medium" | "low"
    in_scope: bool
    escalation_flag: bool
    escalation_reason: Optional[str]

    # ── Customer Context ─────────────────────────────────────────────────────
    # customer_type is SELF-DECLARED by the customer — never verified.
    # Accepted in good faith per business policy (see discounts config).
    customer_type: str                  # "new" | "returning"
    boiler_brand: Optional[str]         # confirmed supported brand (Vaillant/Baxi/Ideal)
    postcode: Optional[str]
    ulez_zone: Optional[str]            # "inner" | "outer" | "outside"

    # ── Availability ─────────────────────────────────────────────────────────
    urgency_tier: Optional[str]         # "same_day" | "evening_weekend" | "next_day"
    availability_slots: List[Dict[str, Any]]

    # ── Pricing ──────────────────────────────────────────────────────────────
    base_price: Optional[float]
    urgency_multiplier: float
    ulez_surcharge: float
    parts_estimate: float
    calculated_price: Optional[float]   # base × multiplier + ulez + parts

    # ── Negotiation ──────────────────────────────────────────────────────────
    negotiation_round: int
    floor_price: Optional[float]
    discount_pct: float
    final_price: Optional[float]        # calculated_price after discount
    competitor_match_attempted: bool

    # ── Authority ────────────────────────────────────────────────────────────
    authority_level: Optional[str]      # "auto_confirm" | "human_review" | "hard_block"

    # ── Output ───────────────────────────────────────────────────────────────
    quote_reference: Optional[str]
    quote_validity_hours: int
    quote_issued: bool

    # ── Self-help ─────────────────────────────────────────────────────────────
    # True after the agent has shown self-help steps for this job.
    # On the next turn, the agent skips self-help and issues the quote.
    self_help_offered: bool
    # True when self-help failed and we're waiting for a postcode before
    # building the diagnostic visit quote.
    pending_self_help_quote: bool

    # ── Booking ───────────────────────────────────────────────────────────────
    # True after the customer has confirmed an appointment slot.
    booking_confirmed: bool

    # ── Error recovery ───────────────────────────────────────────────────────
    error_state: Optional[str]
    retry_count: int


def initial_state(session_id: str, customer_name: str, customer_type: str = "new") -> Dict[str, Any]:
    """Returns a fully-populated initial state dict for a new session."""
    return {
        "messages": [],
        "session_id": session_id,
        "customer_name": customer_name,
        "safety_triggered": False,
        "safety_type": None,
        "intent": None,
        "phase": "intake",
        "diagnostic_questions_asked": 0,
        "symptoms": [],
        "diagnostic_complete": False,
        "next_diagnostic_question": None,
        "job_type": None,
        "confidence_level": None,
        "in_scope": True,
        "escalation_flag": False,
        "escalation_reason": None,
        "customer_type": customer_type,
        "boiler_brand": None,
        "postcode": None,
        "ulez_zone": None,
        "urgency_tier": None,
        "availability_slots": [],
        "urgency_multiplier": 1.0,
        "ulez_surcharge": 0.0,
        "parts_estimate": 0.0,
        "base_price": None,
        "calculated_price": None,
        "negotiation_round": 0,
        "floor_price": None,
        "discount_pct": 0.0,
        "final_price": None,
        "competitor_match_attempted": False,
        "authority_level": None,
        "quote_reference": None,
        "quote_validity_hours": 24,
        "quote_issued": False,
        "self_help_offered": False,
        "pending_self_help_quote": False,
        "booking_confirmed": False,
        "error_state": None,
        "retry_count": 0,
    }
