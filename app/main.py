"""
FixFlow FastAPI application.

Endpoints:
  POST /api/session/start  — create a new quote session
  POST /api/chat           — send a message to the agent
  GET  /api/quotes         — retrieve quotes issued in the current session
  GET  /health             — liveness probe

Authentication: none (demo only — all endpoints are open).
Data storage: in-memory only; clears on server restart.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

load_dotenv()

from pathlib import Path

from app.graph import get_graph
from app.config import load_business_config
from app.state import initial_state

app = FastAPI(title="FixFlow API", version="1.0.0", docs_url="/docs")

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(_FRONTEND_DIR / "index.html")


# In-memory quote store: session_id → list of quote dicts
# (quotes are also stored in LangGraph state, but this provides a simple
# /api/quotes endpoint without replaying the full graph)
_quotes: Dict[str, List[Dict[str, Any]]] = {}


# ── Request / Response models ─────────────────────────────────────────────────

class StartRequest(BaseModel):
    customer_name: str
    is_returning: bool = False


class StartResponse(BaseModel):
    session_id: str
    customer_name: str
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

    biz = load_business_config()
    brands = ", ".join(biz["supported_brands"])

    if req.is_returning:
        welcome = (
            f"Welcome back, {req.customer_name}! Great to see you again. "
            "As a returning customer, your loyalty discount will be automatically applied to your quote. "
            f"We service {brands} boilers across London — what can we help you with today?"
        )
    else:
        welcome = (
            f"Hi {req.customer_name}! I'm FixFlow, your 24/7 plumbing and boiler quote assistant. "
            f"We cover emergency plumbing repairs, boiler servicing, repairs, and replacements for "
            f"{brands} boilers across London. "
            "Describe your problem and I'll have a quote ready for you in under 60 seconds."
        )
    return StartResponse(session_id=session_id, customer_name=req.customer_name, message=welcome)


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


@app.get("/graph", response_class=HTMLResponse, include_in_schema=False)
async def view_graph() -> HTMLResponse:
    """
    Render the LangGraph conditional-edge diagram as an interactive Mermaid chart.
    Visit http://localhost:8000/graph in a browser to see the full routing map.
    """
    mermaid_src = get_graph().get_graph(xray=False).draw_mermaid()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>FixFlow — Agent Graph</title>
  <style>
    body {{ margin: 0; background: #0f1117; display: flex; flex-direction: column;
           align-items: center; font-family: system-ui, sans-serif; color: #e2e8f0; }}
    h1   {{ margin: 24px 0 8px; font-size: 1.3rem; letter-spacing: .05em; }}
    p    {{ margin: 0 0 20px; font-size: .85rem; color: #94a3b8; }}
    #graph {{ background: #1e2130; border-radius: 12px; padding: 24px;
              max-width: 98vw; overflow: auto; box-shadow: 0 4px 24px #0008; }}
    .mermaid {{ min-width: 700px; }}
  </style>
</head>
<body>
  <h1>FixFlow — Agent Routing Graph</h1>
  <p>Conditional edges show every path the agent can take through its 11 nodes.</p>
  <div id="graph">
    <div class="mermaid">
{mermaid_src}
    </div>
  </div>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
    mermaid.initialize({{ startOnLoad: true, theme: 'dark', flowchart: {{ curve: 'basis' }} }});
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)
