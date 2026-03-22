"""
LangGraph graph definition for FixFlow.

Phase-based routing — each turn enters the graph at the correct node:

  EVERY TURN:
    START → input_guard
              ├─ safety triggered ─────────────────────────────────────────► output_guard → END
              └─ safe → phase router
                            │
                            ├─ phase="intake"          → intent_classifier
                            │       ├─ non-quote       → output_guard → END
                            │       └─ quote_request   → diagnostic
                            │                               ├─ incomplete → output_guard → END
                            │                               └─ complete   → job_classifier
                            │                                                   ├─ out of scope → output_guard → END
                            │                                                   ├─ escalation   → authority_check → output_guard → END
                            │                                                   └─ in scope     → availability → pricing → negotiation → authority_check → output_guard → END
                            │
                            ├─ phase="diagnosis"       → diagnostic (same sub-graph as above)
                            │
                            ├─ phase="quoting"           → negotiation → authority_check → output_guard → END
                            ├─ phase="self_help"         → self_help_followup → output_guard → END
                            ├─ phase="negotiating"       → negotiation → authority_check → output_guard → END
                            ├─ phase="awaiting_postcode" → postcode_capture → pricing → negotiation → authority_check → output_guard → END
                            │
                            └─ phase="escalated"/"ended" → output_guard → END

Key property: turns 2+ in diagnosis skip intent_classifier entirely.
Turns in quoting/negotiating skip diagnosis, classification, availability, pricing.
LangSmith traces show only the nodes that actually ran.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.nodes.authority_check import authority_check_node
from app.nodes.availability import availability_node
from app.nodes.diagnostic import diagnostic_node
from app.nodes.input_guard import input_guard_node
from app.nodes.intent_classifier import intent_classifier_node
from app.nodes.job_classifier import job_classifier_node
from app.nodes.negotiation import negotiation_node
from app.nodes.output_guard import output_guard_node
from app.nodes.postcode_capture import postcode_capture_node
from app.nodes.pricing import pricing_node
from app.nodes.self_help_followup import self_help_followup_node
from app.state import QuoteState


# ── Conditional routing functions ────────────────────────────────────────────

def _route_input_guard(state: QuoteState) -> str:
    """
    Primary phase-based router — the core of the graph's conditional logic.

    Routes to the correct entry node based on where the conversation currently is,
    rather than always walking the full pipeline. This means:
      - turn 2 of a diagnosis goes straight to `diagnostic` (skips intent_classifier)
      - a quoting turn goes straight to `negotiation` (skips diagnosis/pricing)
      - completed or safety-triggered sessions go to `output_guard`
    """
    if state.get("safety_triggered"):
        return "output_guard"

    phase = state.get("phase", "intake")

    if phase == "intake":
        # First message — classify intent, then begin diagnosis
        return "intent_classifier"

    if phase == "diagnosis":
        # Mid-diagnosis — go straight to diagnostic node
        return "diagnostic"

    if phase in ("quoting", "negotiating", "booked"):
        # Quote has been issued (or booking confirmed) — route through negotiation
        # so the customer can reschedule, ask questions, or accept a re-quote.
        return "negotiation"

    if phase == "self_help":
        # DIY steps were shown — check if they worked
        return "self_help_followup"

    if phase == "awaiting_postcode":
        # Customer is replying with their postcode
        return "postcode_capture"

    # "escalated", "ended", or any unrecognised phase
    return "output_guard"


def _route_intent(state: QuoteState) -> str:
    # If conversation ended (escalation, safety, etc.), no more processing
    if state.get("phase") in ("ended", "escalated"):
        return "output_guard"
    intent = state.get("intent")
    # Farewell always goes to output_guard regardless of quote state
    if intent == "farewell":
        return "output_guard"
    # If quote already issued, skip to negotiation (handles pushback + slot selection)
    if state.get("quote_issued"):
        return "negotiation"
    if intent in ("greeting", "general_enquiry", "complaint", "emergency"):
        return "output_guard"
    return "diagnostic"


def _route_diagnostic(state: QuoteState) -> str:
    if not state.get("diagnostic_complete"):
        return "output_guard"
    return "job_classifier"


def _route_job_classifier(state: QuoteState) -> str:
    if not state.get("in_scope", True):
        return "output_guard"
    if state.get("escalation_flag"):
        return "authority_check"
    return "availability"


# ── Graph builder ────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    builder = StateGraph(QuoteState)

    builder.add_node("input_guard", input_guard_node)
    builder.add_node("intent_classifier", intent_classifier_node)
    builder.add_node("diagnostic", diagnostic_node)
    builder.add_node("job_classifier", job_classifier_node)
    builder.add_node("availability", availability_node)
    builder.add_node("pricing", pricing_node)
    builder.add_node("negotiation", negotiation_node)
    builder.add_node("authority_check", authority_check_node)
    builder.add_node("output_guard", output_guard_node)
    builder.add_node("self_help_followup", self_help_followup_node)
    builder.add_node("postcode_capture", postcode_capture_node)

    builder.add_edge(START, "input_guard")
    builder.add_conditional_edges(
        "input_guard",
        _route_input_guard,
        {
            "intent_classifier":  "intent_classifier",
            "diagnostic":         "diagnostic",
            "negotiation":        "negotiation",
            "self_help_followup": "self_help_followup",
            "postcode_capture":   "postcode_capture",
            "output_guard":       "output_guard",
        },
    )
    builder.add_conditional_edges(
        "intent_classifier",
        _route_intent,
        {
            "output_guard": "output_guard",
            "diagnostic":   "diagnostic",
        },
    )
    builder.add_conditional_edges(
        "diagnostic",
        _route_diagnostic,
        {
            "output_guard":   "output_guard",
            "job_classifier": "job_classifier",
        },
    )
    builder.add_conditional_edges(
        "job_classifier",
        _route_job_classifier,
        {
            "output_guard":   "output_guard",
            "authority_check": "authority_check",
            "availability":   "availability",
        },
    )
    builder.add_edge("availability", "pricing")
    builder.add_edge("pricing", "negotiation")
    builder.add_edge("negotiation", "authority_check")
    builder.add_edge("authority_check", "output_guard")
    builder.add_edge("self_help_followup", "output_guard")
    builder.add_edge("postcode_capture", "pricing")
    builder.add_edge("output_guard", END)

    return builder


# ── Singleton compiled graph with in-memory checkpointer ────────────────────

_memory = MemorySaver()
_graph = None


def get_graph():
    """Return the compiled graph singleton (lazy initialisation)."""
    global _graph
    if _graph is None:
        _graph = build_graph().compile(checkpointer=_memory)
    return _graph
