"""
LangGraph graph definition for FixFlow.

Cyclic graph with interrupt-based multi-turn conversation:

  Turn 1 (first message):
    START → input_guard → (phase router) → ... → output_guard
              │                                        │
              │              ┌─ terminal (ended/escalated) → END
              │              │
              │              └─ continuing → wait_for_input ──┐
              │                     ▲            (interrupt)  │
              │                     │                         │
              └─────────────────────┴─────────────────────────┘
                              (loop back)

  Turn 2+ (resume from interrupt with new message):
    wait_for_input → input_guard → (phase router) → ... → output_guard
                                                              │
                                   ┌─ terminal → END          │
                                   │                          │
                                   └─ continuing → wait_for_input (interrupt)

  Phase router (input_guard):
    ├─ intake            → intent_classifier
    │       ├─ non-quote       → output_guard
    │       └─ quote_request   → diagnostic
    │                               ├─ incomplete → output_guard
    │                               └─ complete   → job_classifier
    │                                                   ├─ out of scope → output_guard
    │                                                   ├─ escalation   → authority_check → output_guard
    │                                                   └─ in scope     → availability → pricing → negotiation → authority_check → output_guard
    ├─ diagnosis         → diagnostic (loops back for each question)
    ├─ quoting           → negotiation → authority_check → output_guard (loops for pushback rounds)
    ├─ negotiating       → negotiation → authority_check → output_guard
    ├─ booked            → output_guard (resets to intake, loops back)
    ├─ self_help         → self_help_followup → output_guard (loops for clarification)
    ├─ awaiting_postcode → postcode_capture
    │                         ├─ success → pricing → ... → output_guard
    │                         └─ failure → output_guard (loops for retry)
    └─ escalated/ended   → output_guard → END

Visible loops in LangSmith Studio:
  • Diagnostic loop     — output_guard → wait → input_guard → diagnostic → output_guard
  • Negotiation loop    — output_guard → wait → input_guard → negotiation → ... → output_guard
  • Postcode retry loop — output_guard → wait → input_guard → postcode_capture → output_guard
  • Self-help loop      — output_guard → wait → input_guard → self_help_followup → output_guard
  • Session restart     — output_guard → wait → input_guard → intent_classifier → diagnostic → ...
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

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


# ── Wait-for-input node (interrupt point) ────────────────────────────────────

def wait_for_input_node(state: QuoteState) -> dict:
    """Pause the graph and wait for the next human message.

    This node is the loop-back point between turns. After output_guard
    delivers a response, continuing (non-terminal) conversations route
    here. The interrupt() call pauses execution; on resume, the graph
    continues to input_guard with the new message in state.
    """
    interrupt("waiting_for_user_input")
    return {}


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

    if phase in ("quoting", "negotiating"):
        # Quote has been issued — route through negotiation
        # so the customer can reschedule, ask questions, or accept a re-quote.
        return "negotiation"

    if phase == "booked":
        # Booking confirmed — go straight to output_guard (no LLM needed).
        # output_guard resets to intake, so the next turn re-classifies via
        # intent_classifier. If quote_issued is True, _route_intent sends
        # to negotiation, preserving reschedule/follow-up capability.
        return "output_guard"

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


def _route_postcode_capture(state: QuoteState) -> str:
    """Route after postcode capture: success → pricing, failure → output_guard.

    On failure the node sets a retry carrier message and keeps
    phase="awaiting_postcode". Routing to output_guard directly avoids
    running pricing/negotiation/authority_check needlessly.
    """
    if state.get("postcode_captured"):
        return "pricing"
    return "output_guard"


def _route_output_guard(state: QuoteState) -> str:
    """Route after output_guard: terminal phases end the graph,
    continuing phases loop back via wait_for_input → input_guard.

    This creates visible cycles in the LangSmith Studio graph for:
      • diagnostic multi-question loop
      • negotiation pushback rounds
      • postcode retry loop
      • self-help clarification loop
      • session restart (out-of-scope / post-booking → new request)
    """
    phase = state.get("phase", "intake")
    if phase in ("ended", "escalated"):
        return "__end__"
    return "wait_for_input"


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
    builder.add_node("wait_for_input", wait_for_input_node)

    # ── Entry ─────────────────────────────────────────────────────────────────
    builder.add_edge(START, "input_guard")

    # ── input_guard → phase-based routing ─────────────────────────────────────
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

    # ── intent_classifier → diagnostic / negotiation / output_guard ───────────
    builder.add_conditional_edges(
        "intent_classifier",
        _route_intent,
        {
            "output_guard": "output_guard",
            "diagnostic":   "diagnostic",
            "negotiation":  "negotiation",
        },
    )

    # ── diagnostic → output_guard (question) / job_classifier (complete) ──────
    builder.add_conditional_edges(
        "diagnostic",
        _route_diagnostic,
        {
            "output_guard":   "output_guard",
            "job_classifier": "job_classifier",
        },
    )

    # ── job_classifier → availability / authority_check / output_guard ────────
    builder.add_conditional_edges(
        "job_classifier",
        _route_job_classifier,
        {
            "output_guard":    "output_guard",
            "authority_check": "authority_check",
            "availability":    "availability",
        },
    )

    # ── Linear pipeline: availability → pricing → negotiation → authority ────
    builder.add_edge("availability", "pricing")
    builder.add_edge("pricing", "negotiation")
    builder.add_edge("negotiation", "authority_check")
    builder.add_edge("authority_check", "output_guard")

    # ── self_help_followup → output_guard ─────────────────────────────────────
    builder.add_edge("self_help_followup", "output_guard")

    # ── postcode_capture → pricing (success) / output_guard (failure) ────────
    builder.add_conditional_edges(
        "postcode_capture",
        _route_postcode_capture,
        {
            "pricing":      "pricing",
            "output_guard": "output_guard",
        },
    )

    # ── output_guard → END (terminal) or wait_for_input (loop back) ──────────
    builder.add_conditional_edges(
        "output_guard",
        _route_output_guard,
        {
            "__end__":         END,
            "wait_for_input":  "wait_for_input",
        },
    )

    # ── wait_for_input → input_guard (the backward loop edge) ────────────────
    builder.add_edge("wait_for_input", "input_guard")

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
