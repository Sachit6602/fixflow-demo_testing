"""
LangGraph graph definition for FixFlow.

9-node stateful graph with conditional edges:

  START
    └─► input_guard
          ├─ safety triggered ──────────────────────────────────► output_guard ─► END
          └─ safe ─► intent_classifier
                          ├─ non-quote intent ──────────────────► output_guard ─► END
                          └─ quote_request ─► diagnostic
                                                ├─ incomplete ──► output_guard ─► END
                                                └─ complete ─► job_classifier
                                                                    ├─ out of scope ► output_guard ─► END
                                                                    ├─ escalation ──► authority_check ─► output_guard ─► END
                                                                    └─► availability ─► pricing
                                                                                           └─► negotiation
                                                                                                  └─► authority_check
                                                                                                         └─► output_guard ─► END

State is persisted between turns via LangGraph MemorySaver (keyed by session_id).
Each /api/chat call invokes the graph with the new user message appended; the
add_messages reducer accumulates conversation history automatically.
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
from app.nodes.pricing import pricing_node
from app.state import QuoteState


# ── Conditional routing functions ────────────────────────────────────────────

def _route_input_guard(state: QuoteState) -> str:
    return "output_guard" if state.get("safety_triggered") else "intent_classifier"


def _route_intent(state: QuoteState) -> str:
    intent = state.get("intent")
    if intent in ("general_enquiry", "complaint", "emergency"):
        return "output_guard"
    return "diagnostic"


def _route_diagnostic(state: QuoteState) -> str:
    # If not yet complete (and a question is queued), surface it via output_guard.
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

    builder.add_edge(START, "input_guard")
    builder.add_conditional_edges("input_guard", _route_input_guard)
    builder.add_conditional_edges("intent_classifier", _route_intent)
    builder.add_conditional_edges("diagnostic", _route_diagnostic)
    builder.add_conditional_edges("job_classifier", _route_job_classifier)
    builder.add_edge("availability", "pricing")
    builder.add_edge("pricing", "negotiation")
    builder.add_edge("negotiation", "authority_check")
    builder.add_edge("authority_check", "output_guard")
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
