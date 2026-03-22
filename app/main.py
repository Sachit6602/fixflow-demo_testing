"""
FixFlow FastAPI application.

Endpoints:
  POST /api/session/start       — create a new quote session (web frontend)
  POST /api/session/start-luffa — create a session with Luffa uid (auto-detects returning users)
  GET  /api/session/lookup      — look up active session by Luffa uid
  POST /api/chat                — send a message to the agent
  GET  /api/quotes              — retrieve quotes issued in the current session
  GET  /health                  — liveness probe

Authentication: none (demo only — all endpoints are open).
Data storage: quotes persisted to Supabase; session state in-memory via LangGraph MemorySaver.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

load_dotenv()

from pathlib import Path

from app.graph import get_graph
from app.state import initial_state

app = FastAPI(title="FixFlow API", version="1.0.0", docs_url="/docs")

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(_FRONTEND_DIR / "index.html")


# In-memory quote store: session_id → list of quote dicts
_quotes: Dict[str, List[Dict[str, Any]]] = {}

# Luffa uid ↔ session_id mappings (in-memory, for active sessions only)
_uid_sessions: Dict[str, str] = {}   # luffa_uid → session_id
_session_uids: Dict[str, str] = {}   # session_id → luffa_uid

# Track session start times for response time calculation
_session_start_times: Dict[str, float] = {}  # session_id → timestamp


def _log_safe(fn, *args, **kwargs):
    """Call a persistence function, swallowing errors so they never break the API."""
    try:
        fn(*args, **kwargs)
    except Exception as e:
        print(f"[Dashboard] {fn.__name__} failed: {e}")


# ── Request / Response models ─────────────────────────────────────────────────

class StartRequest(BaseModel):
    customer_name: str
    is_returning: bool = False


class StartResponse(BaseModel):
    session_id: str
    customer_name: str
    message: str


class LuffaStartRequest(BaseModel):
    luffa_uid: str
    customer_name: str = "Customer"


class LuffaStartResponse(BaseModel):
    session_id: str
    is_returning: bool
    message: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    response: str
    phase: Optional[str] = None
    quote_reference: Optional[str] = None
    error: Optional[str] = None


class QuotesResponse(BaseModel):
    session_id: str
    quotes: List[Dict[str, Any]]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/api/session/start", response_model=StartResponse)
async def start_session(req: StartRequest) -> StartResponse:
    """
    Create a new quote session and initialise the LangGraph checkpoint.
    Returns a session_id to use in subsequent /api/chat calls.
    """
    session_id = str(uuid.uuid4())
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}

    # Write the initial state directly to the checkpoint — no nodes run.
    # Using update_state instead of invoke avoids the intent_classifier being
    # called with an empty message list, which would misclassify as general_enquiry.
    customer_type = "returning" if req.is_returning else "new"
    seed = initial_state(session_id=session_id, customer_name=req.customer_name, customer_type=customer_type)
    graph.update_state(config, seed)

    _quotes[session_id] = []

    if req.is_returning:
        welcome = (
            f"Welcome back, {req.customer_name}! Great to see you again. "
            "As a returning customer, your loyalty discount will be automatically applied to your quote. "
            "What can we help you with today?"
        )
    else:
        welcome = (
            f"Hi {req.customer_name}! I'm FixFlow, your 24/7 plumbing and boiler quote assistant. "
            "Describe your problem and I'll have a quote ready for you in under 60 seconds."
        )
    return StartResponse(session_id=session_id, customer_name=req.customer_name, message=welcome)


@app.post("/api/session/start-luffa", response_model=LuffaStartResponse)
async def start_luffa_session(req: LuffaStartRequest) -> LuffaStartResponse:
    """
    Create a new quote session using a Luffa uid.
    Automatically detects returning users via Supabase quote history.
    """
    from app import persistence

    persistence.get_or_create_user(req.luffa_uid, req.customer_name)
    is_returning = persistence.is_returning_user(req.luffa_uid)
    customer_type = "returning" if is_returning else "new"

    session_id = str(uuid.uuid4())
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}

    seed = initial_state(
        session_id=session_id,
        customer_name=req.customer_name,
        customer_type=customer_type,
        luffa_uid=req.luffa_uid,
    )
    graph.update_state(config, seed)

    _quotes[session_id] = []
    _uid_sessions[req.luffa_uid] = session_id
    _session_uids[session_id] = req.luffa_uid
    _session_start_times[session_id] = time.time()

    # Dashboard: record chat session + event
    _log_safe(persistence.create_chat, session_id, req.luffa_uid, req.customer_name, customer_type)
    _log_safe(persistence.log_event, session_id, "chat_started",
              {"customer_type": customer_type, "is_returning": is_returning}, req.luffa_uid)

    if is_returning:
        welcome = (
            f"Welcome back, {req.customer_name}! Great to see you again. "
            "As a returning customer, your loyalty discount will be automatically applied to your quote. "
            "What can we help you with today?"
        )
    else:
        welcome = (
            f"Hi {req.customer_name}! I'm FixFlow, your 24/7 plumbing and boiler quote assistant. "
            "Describe your problem and I'll have a quote ready for you in under 60 seconds."
        )

    return LuffaStartResponse(session_id=session_id, is_returning=is_returning, message=welcome)


@app.get("/api/session/lookup")
async def lookup_session(luffa_uid: str) -> Dict[str, str]:
    """Look up the active session for a Luffa user."""
    session_id = _uid_sessions.get(luffa_uid)
    if not session_id:
        raise HTTPException(status_code=404, detail="No active session for this user.")
    return {"session_id": session_id}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """
    Send a customer message to the agent and receive a response.
    Maintains full conversation state across turns via LangGraph MemorySaver.
    """
    graph = get_graph()
    config = {"configurable": {"thread_id": req.session_id}}

    # Verify the session exists
    snapshot = graph.get_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Please call /api/session/start first.",
        )

    try:
        result = graph.invoke(
            {"messages": [HumanMessage(content=req.message)]},
            config=config,
        )
    except Exception as exc:
        # Surface the error to the caller rather than silently failing
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    # Extract the latest AI message from the result
    ai_response = ""
    for msg in reversed(result.get("messages", [])):
        if getattr(msg, "type", None) == "ai":
            ai_response = msg.content
            break

    if not ai_response:
        ai_response = (
            "I'm having trouble with your request right now. "
            "Please try again or call us directly."
        )

    # Dashboard: update chat session with latest state
    luffa_uid = _session_uids.get(req.session_id)
    if luffa_uid:
        from app import persistence

        chat_updates = {
            "phase": result.get("phase"),
            "message_count": len([m for m in result.get("messages", []) if getattr(m, "type", None) == "human"]),
            "postcode": result.get("postcode"),
            "intent": result.get("intent"),
            "diagnostic_questions_asked": result.get("diagnostic_questions_asked", 0),
        }

        # Log safety triggers
        if result.get("safety_triggered"):
            _log_safe(persistence.log_event, req.session_id, "safety_trigger", {
                "safety_type": result.get("safety_type"),
            }, luffa_uid)

        # Log escalations
        if result.get("phase") == "escalated":
            _log_safe(persistence.log_event, req.session_id, "escalation", {
                "reason": result.get("escalation_reason"),
                "authority_level": result.get("authority_level"),
            }, luffa_uid)

        # Log out-of-scope
        if not result.get("in_scope", True) and result.get("job_type"):
            _log_safe(persistence.log_event, req.session_id, "out_of_scope", {
                "job_type": result.get("job_type"),
            }, luffa_uid)

        # Log negotiation rounds
        if result.get("negotiation_round", 0) > 0:
            floor = result.get("floor_price") or 0
            final = result.get("final_price") or 0
            _log_safe(persistence.log_event, req.session_id, "negotiation_round", {
                "round": result.get("negotiation_round"),
                "discount_pct": result.get("discount_pct", 0),
                "competitor_match": result.get("competitor_match_attempted", False),
                "floor_hit": final <= floor if final and floor else False,
            }, luffa_uid)

        # Log conversation ended
        if result.get("phase") in ("ended", "escalated"):
            chat_updates["ended_at"] = "now()"
            _log_safe(persistence.log_event, req.session_id, "chat_ended", {
                "phase": result.get("phase"),
            }, luffa_uid)

        _log_safe(persistence.update_chat, req.session_id, chat_updates)

    # Record quote if one was just issued
    if result.get("quote_issued") and result.get("quote_reference"):
        ref = result["quote_reference"]
        existing = _quotes.get(req.session_id, [])
        if not any(q["reference"] == ref for q in existing):
            existing.append({
                "reference": ref,
                "job_type": result.get("job_type"),
                "final_price": result.get("final_price"),
                "authority_level": result.get("authority_level"),
                "validity_hours": result.get("quote_validity_hours", 24),
                "confidence": result.get("confidence_level"),
            })
            _quotes[req.session_id] = existing

            # Calculate response time (first message to first quote)
            response_time = None
            start_ts = _session_start_times.get(req.session_id)
            if start_ts:
                response_time = round(time.time() - start_ts, 1)

            # Persist to Supabase if this is a Luffa session
            luffa_uid = _session_uids.get(req.session_id)
            if luffa_uid:
                from app import persistence
                _log_safe(persistence.record_quote,
                    uid=luffa_uid,
                    session_id=req.session_id,
                    quote_ref=ref,
                    job_type=result.get("job_type"),
                    final_price=result.get("final_price"),
                    extra={
                        "confidence_level": result.get("confidence_level"),
                        "authority_level": result.get("authority_level"),
                        "base_price": result.get("base_price"),
                        "urgency_tier": result.get("urgency_tier"),
                        "urgency_multiplier": result.get("urgency_multiplier"),
                        "ulez_zone": result.get("ulez_zone"),
                        "ulez_surcharge": result.get("ulez_surcharge"),
                        "discount_pct": result.get("discount_pct", 0),
                        "customer_type": result.get("customer_type"),
                        "postcode": result.get("postcode"),
                    },
                )
                _log_safe(persistence.log_event, req.session_id, "quote_issued", {
                    "quote_ref": ref,
                    "final_price": result.get("final_price"),
                    "job_type": result.get("job_type"),
                    "authority_level": result.get("authority_level"),
                }, luffa_uid)
                _log_safe(persistence.update_chat, req.session_id, {
                    "quote_issued": True,
                    "quote_reference": ref,
                    "first_quote_at": "now()",
                    "response_time_seconds": response_time,
                })

    return ChatResponse(
        session_id=req.session_id,
        response=ai_response,
        phase=result.get("phase"),
        quote_reference=result.get("quote_reference"),
        error=result.get("error_state"),
    )


@app.get("/api/quotes", response_model=QuotesResponse)
async def get_quotes(session_id: str) -> QuotesResponse:
    """Return all quotes issued during the given session (in-memory only)."""
    if session_id not in _quotes:
        raise HTTPException(status_code=404, detail="Session not found.")
    return QuotesResponse(session_id=session_id, quotes=_quotes[session_id])


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": "FixFlow API"}
