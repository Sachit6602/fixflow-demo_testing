# FixFlow

Autonomous AI quoting agent for emergency plumbing and boiler services. Handles the full quoting workflow — symptom diagnosis, job classification, live availability, dynamic pricing, negotiation, and authority enforcement — without human involvement, 24/7.

Built as a reference implementation for a London-based trades business (5-20 engineers). A quote is returned in under 60 seconds from first message.

## Architecture

**Stack:** FastAPI + LangGraph + Claude Haiku 4.5 (via OpenRouter) + LangSmith tracing + Supabase persistence + Civic MCP

FixFlow is a cyclic LangGraph state machine with 11 nodes, driven by a shared `QuoteState` (40+ fields). Every node reads from and writes to this typed state contract — no hidden side channels.

![FixFlow LangGraph Architecture](Screenshot%202026-03-22%20052808.png)

### Nodes

| Node | Purpose |
|------|---------|
| **Input Guard** | Safety gate on every turn. Detects gas leaks (hard stop + emergency redirect) and prompt injection (Civic Bodyguard primary, regex + LLM fallback). |
| **Intent Classifier** | Routes first message: quote request, general enquiry, complaint, or emergency. |
| **Diagnostic** | Structured symptom extraction, max 5 questions. Produces symptoms list for job classification. |
| **Job Classifier** | Maps symptoms to job type with confidence level. Validates brand/scope against business config. |
| **Postcode Capture** | Extracts UK postcode, geocodes via postcodes.io, determines ULEZ zone for surcharges. |
| **Availability** | Three-tier slot resolution: (1) Live Google Calendar via Civic MCP, (2) dynamic geocoded slots from engineer schedules, (3) static fallback. |
| **Pricing** | Calculates price: base rate x urgency multiplier + ULEZ surcharge + parts estimate. Sets floor price. |
| **Negotiation** | Detects pushback, booking intent, reschedule requests, self-help queries, and cheaper-slot requests via LLM structured output. Enforces floor price and max discount caps. |
| **Authority Check** | Deterministic three-tier authority model: auto-confirm (< £300), human review (£300-£800), hard block (> £800 or escalation). No LLM involved. |
| **Self-Help Followup** | Returns DIY steps for applicable jobs, then offers professional quote if customer still needs help. |
| **Output Guard** | Formats final AI response, applies PII redaction, appends to conversation history. |

### The 5 Loops (What Makes It an Agent, Not a Pipeline)

| Loop | What Happens | Example |
|------|-------------|---------|
| **Diagnostic** | Agent asks up to 5 questions to understand the problem | "What brand?" -> "What error code?" -> "How long?" |
| **Negotiation** | Customer pushes back on price, agent offers capped discounts | "Too expensive" -> 10% off -> "That's my best offer" |
| **Postcode Retry** | Agent needs postcode for ULEZ pricing, asks until valid | "What's your postcode?" -> "That's not London" -> retry |
| **Self-Help** | Agent offers DIY fix first, checks if it worked | Steps shown -> "Did it work?" -> "No" -> engineer visit |
| **Session Restart** | After any resolution, customer can start a new request | Booking done -> "Anything else?" -> new diagnostic |

## Autonomy Scorecard

### What's Fully Autonomous (zero human involvement)

| Decision | How It Works | Human Needed? |
|----------|-------------|---------------|
| Safety detection (gas/injection) | 2-layer: regex + LLM fallback | No |
| Intent classification | LLM classifies 6 intent types | No |
| Diagnostic questioning | LLM asks up to 5 Qs, brand gate, symptom extraction | No |
| Job classification + confidence | LLM maps symptoms to job type | No |
| Scope validation | Checked against `business_config.json`, not LLM | No |
| Availability slots | Geocoding + haversine travel time + engineer schedules | No |
| Pricing | Deterministic formula: (base x urgency) + ULEZ + parts | No |
| Self-help flow | Offers DIY, classifies outcome, falls back to engineer visit | No |
| Negotiation (2 rounds) | LLM negotiates with config-enforced floor + discount caps | No |
| Auto-confirm booking (<£300) | Deterministic authority check, no LLM | No |
| Returning user detection | Supabase uid lookup, loyalty discount auto-applied | No |
| Postcode + ULEZ calculation | Regex extraction + config lookup, no LLM | No |
| PII masking | Strips postcodes/phones before every LLM call | No |
| Session lifecycle | Greeting, farewell, timeout, /end — all handled | No |
| Out-of-scope recovery | Graceful decline + state reset for new request in same session | No |

### Where It Hands Off to Humans (by design)

| Trigger | What Happens | Why |
|---------|-------------|-----|
| Gas smell detected | Hard stop -> "Call 0800 111 999" | Safety — human must intervene |
| Quote £300-£800 | Says "a specialist will follow up in 2 hours" | Business risk |
| Quote >£800 or replacement | Hard block -> "call us at 020 7946 0000" | Too complex for auto |
| Unsupported brand | Graceful decline -> suggests manufacturer service network | Out of scope |

### Known Gaps

| Gap | What It Says | What Actually Happens |
|-----|-------------|----------------------|
| Human review tier (£300-£800) | "A specialist will follow up within 2 hours" | No notification system exists — the quote sits in state with no queue or alert |
| Hard block escalation | "A specialist will contact you" | No ticket created — customer is given a phone number to call themselves |
| Engineer dispatch | "Our engineer will call 30 minutes before arrival" | No dispatch system — `engineers.json` is static demo data |
| Payment | Luffa bot triggers payment flow | Delegates to external `payment.py` module — no confirmation loop back to agent |
| Booking persistence | Booking "confirmed" in chat | Now written to Google Calendar via Civic MCP |

## Integrations

### Civic MCP

FixFlow integrates with [Civic](https://app.civic.com) for two capabilities:

- **Bodyguard** — Prompt injection detection via HTTP API. Primary defence layer; existing regex + LLM checks serve as fallback when Civic is unreachable.
- **Google Calendar** — Live engineer availability and booking confirmation via Civic's MCP hub using `langchain-mcp-adapters`. Availability node queries `google-calendar-query_freebusy` for real free slots. Booking creates a calendar event via `google-calendar-create_event`.

### Luffa

WhatsApp bot integration. Customers can interact with FixFlow through WhatsApp via the Luffa adapter. Returning customer status is auto-detected via Luffa UID history.

### Supabase

Session persistence and quote history. Conversation state is checkpointed to Supabase so sessions survive server restarts.

### LangSmith

Full node-by-node tracing. Every tool call, routing decision, input/output, and latency metric is captured per conversation.

## Demo Scenarios

| # | Scenario | Tests | Outcome |
|---|----------|-------|---------|
| 1 | **Happy path** | Full pipeline | Quote £95 in <60s |
| 2 | **Surge pricing** | Evening/weekend multiplier | £142.50 (x1.5 + ULEZ) |
| 3 | **Negotiation** | Returning customer pushback | 15% discount, floor enforced |
| 4 | **Gas smell** | Safety hard stop | Emergency redirect, no quote |
| 5 | **Replacement** | Authority hard block | Human handoff |
| 6 | **Wrong brand** | Out-of-scope | Graceful decline, no hallucination |

## Setup

### Prerequisites

- Python 3.11+
- OpenRouter API key
- LangSmith API key

### Install

```bash
git clone <repo-url>
cd fixflow-demo_testing
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

Edit `.env` with your values:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key for LLM access |
| `LLM_MODEL` | Yes | Model ID (default: `anthropic/claude-haiku-4-5`) |
| `LANGCHAIN_API_KEY` | Yes | LangSmith API key for tracing |
| `LANGCHAIN_PROJECT` | Yes | Project name in LangSmith UI |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase anon key |
| `SUPABASE_SERVICE_KEY` | Yes | Supabase service role key |
| `CIVIC_KEY` | No | Civic Bodyguard API key (falls back to regex + LLM) |
| `CIVIC_URL` | No | Civic MCP hub URL with account ID and profile (falls back to static slots) |
| `CIVIC_TOKEN` | No | Civic MCP auth token for Google Calendar |
| `LUFFA_SECRET` | No | Luffa bot webhook secret |

### Run

```bash
uvicorn app.main:app --reload
```

The API server starts at `http://localhost:8000`.

### Frontend

A minimal chat UI is included in `frontend/`. Open `frontend/index.html` in a browser or serve it statically.

A Next.js dashboard is available in `dashboard/`:

```bash
cd dashboard
npm install
npm run dev
```

## Project Structure

```
app/
├── main.py              # FastAPI server, chat + session endpoints
├── graph.py             # LangGraph state machine definition
├── state.py             # QuoteState TypedDict (40+ fields)
├── config.py            # Business config, LLM, availability loaders
├── calendar.py          # Google Calendar via Civic MCP
├── civic_guard.py       # Civic Bodyguard prompt injection API
├── geo.py               # Postcode geocoding, ULEZ zone detection
├── persistence.py       # Supabase session checkpointing
├── nodes/               # 11 LangGraph nodes
│   ├── input_guard.py
│   ├── intent_classifier.py
│   ├── diagnostic.py
│   ├── job_classifier.py
│   ├── postcode_capture.py
│   ├── availability.py
│   ├── pricing.py
│   ├── negotiation.py
│   ├── authority_check.py
│   ├── self_help_followup.py
│   └── output_guard.py
├── models/              # Pydantic structured output schemas
└── utils/               # PII redaction, helpers
data/
├── business_config.json # Job types, pricing, thresholds, brands, zones
├── availability.json    # Static fallback slots
└── engineers.json       # Engineer schedules + calendar IDs
frontend/                # Vanilla JS chat UI
dashboard/               # Next.js admin dashboard
luffa/                   # WhatsApp bot adapter
```

## Business Configuration

All business rules live in `data/business_config.json` — not in prompts. This includes:

- Supported job types and base prices
- Supported boiler brands (Vaillant, Baxi, Ideal)
- Coverage zones (London postcodes)
- Urgency tiers and multipliers
- Authority thresholds (auto-confirm, human review, hard block)
- Negotiation rules (max rounds, discount caps, floor price logic)
- Self-help steps per job type

To deploy for a different business, swap the config file. The architecture stays the same.

## License

Hackathon reference implementation. Not for production use.
