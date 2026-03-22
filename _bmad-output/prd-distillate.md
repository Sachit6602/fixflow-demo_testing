---
type: bmad-distillate
sources:
  - "prd.md"
downstream_consumer: "general"
created: "2026-03-20"
updated: "2026-03-22"
token_estimate: 2200
parts: 1
---

## Core Concept
- FixFlow: autonomous AI quoting agent for emergency plumbing/boiler services; London-based reference implementation; handles full quoting loop (symptom diagnosis → job classification → availability → dynamic pricing → negotiation → authority enforcement) without human involvement, 24/7
- Quote returned in <60 seconds from first message
- Target: small-to-medium trades businesses (5–20 engineers) losing out-of-hours quote requests to faster competitors
- End customer: London homeowner/renter in emergency needing immediate credible response at 11pm
- Project type: hackathon demo/reference implementation (NOT production SaaS); no auth, no multi-tenancy
- Category claim: lead qualification, scoping, pricing, negotiation are fully automatable with current tooling
- Stack: FastAPI (Python), LangGraph, Claude Haiku 4.5 (via OpenRouter), LangSmith tracing, Supabase (persistence), Luffa messaging (chat channel)
- Deployment: Railway (single process — FastAPI + Luffa bot polling thread)
- Hackathon: 24-hour build, 3-person team; judged on Autonomy · Usefulness · Technical Depth · Creativity

## Architecture
- 11-node LangGraph stateful graph with phase-based conditional routing and multi-turn conversation
- QuoteState (TypedDict): 40+ field shared state contract; session state in-memory via LangGraph MemorySaver checkpointer; user/quote history persisted to Supabase
- Core Nodes (9): Input Guard, Intent Classifier, Diagnostic Node, Job Classifier, Availability Node, Pricing Node, Negotiation Node, Authority Check, Output Guard
- Added Nodes (2): Postcode Capture (zero-LLM regex extraction), Self-Help Followup (DIY resolution detection)
- Phase-based routing: turns 2+ enter at the correct node based on QuoteState.phase, not replaying the full pipeline; minimises LLM calls per turn
- Phases: intake, diagnosis, quoting, negotiating, awaiting_postcode, self_help, booked, escalated, ended
- business_config.json: sole config surface — supported brands, job types, pricing ranges, coverage zones, negotiation limits; operator modifies rules without changing agent code
- engineers.json: engineer schedules with postcodes for dynamic availability slot generation via postcodes.io geocoding + haversine travel time estimation
- availability.json: static fallback slots when customer postcode unavailable or geocoding fails
- LangSmith: mandatory tracing integration (LANGCHAIN_TRACING_V2=true); node-by-node execution, inputs/outputs, latency; visible to judges in real time
- Channels: Luffa messaging bot (primary demo channel) + REST API + basic web frontend
- Data storage: session state in-memory (LangGraph MemorySaver); user identity and quote history persisted to Supabase for returning-user detection
- PII protection: all LLM-calling nodes use get_safe_messages() to mask postcodes and phone numbers before model processing
- Structured outputs: every LLM call uses Pydantic models (.with_structured_output()) to prevent hallucination and runtime key errors

## API Surface
- POST /api/session/start — create session (web frontend), return session_id and customer_name
- POST /api/session/start-luffa — create session with Luffa uid, auto-detects returning users via Supabase
- GET /api/session/lookup — look up active session by Luffa uid
- POST /api/chat — send message to agent, return agent response with phase and quote reference
- GET /api/quotes — return quotes from current session
- GET /health — liveness probe
- GET /graph — interactive Mermaid diagram of routing logic
- Authentication: none; all endpoints open for demo

## Safety Architecture (structural, not prompt-based)
- Input Guard fires before any other node on every turn; two-layer detection for both gas and injection:
  - Gas detection: Layer 1 keyword regex (zero latency) → Layer 2 LLM classifier fallback for paraphrased descriptions (only when ambiguous signals present)
  - Injection detection: Layer 1 regex patterns for known templates → Layer 2 LLM civic guardrail for social engineering, persona hijacking, hypothetical jailbreaks (only when soft signals detected)
- Gas-smell trigger: hard stop from any node position; returns emergency redirect to Gas Emergency line 0800 111 999; no quote generated, no pricing logic runs
- Gas-smell keyword set covers: sulphur, rotten eggs, gas smell, gas leak, carbon monoxide variants
- Postcode fast-path: when phase="awaiting_postcode", Input Guard skips all LLM calls (regex-only safety checks) — no LLM ever reads the raw postcode
- Authority Check runs after Negotiation — cannot be negotiated away; enforced at architecture level (deterministic, no LLM)
- Scope check in Job Classifier node logic, not LLM prompt — prevents out-of-scope hallucination
- Output Guard: ONLY node that adds AI messages to state; strips internal fields (cost price, margin, capacity data, engineer names)
- /end command: explicit session termination detected in Input Guard before any other processing
- Session timeout: 2-minute inactivity timeout sends notification and clears session
- NFR: gas-smell hard stop must fire on 100% of inputs with gas-leak indicators; 0 false negatives permitted
- NFR: 100% graceful out-of-scope escalation for any service/brand/job/location not in business_config.json; 0 hallucinated responses permitted

## Key Differentiators
- Diagnostic-first: structured diagnostic node with brand gate (must confirm boiler brand before symptom collection); extracts symptoms via max 5-question exchange; produces job classification with confidence level; quotes scoped to actual job not generic range
- Self-help path: for jobs with DIY steps in config, agent shows self-help instructions before quoting; if unresolved, offers discounted diagnostic visit (£65, redeemable against repair)
- Config-bounded scope: agent only knows what business_config.json defines; anything outside (unsupported brands, out-of-area, undefined job types) is escalated not answered
- Full LangSmith observability: judges see node-by-node trace, inputs/outputs, latency, branching logic per conversation; no custom observability infrastructure required
- Authority limits enforced structurally: no quote >£800 auto-confirmed; replacement jobs always escalated
- Returning user detection: automatic via Luffa uid + Supabase quote history; loyalty discount applied without self-declaration; never downgrades uid-verified returning status
- PII-safe LLM calls: postcodes and phone numbers masked before any model invocation; postcode lookup done in pure code
- Dynamic availability: engineer travel time calculated via postcodes.io geocoding + haversine distance; slots sorted by earliest arrival, deduped by hour

## Pricing & Authority Rules
- Urgency tiers: same-day (×1.5), evening/weekend (×1.5), next-day (×1.0), weekday_afternoon (×0.85)
- ULEZ surcharge applied by postcode zone: inner London £15, outer London £10 (longest-prefix matching for accuracy)
- Parts estimate included where applicable (per job type config)
- Medium/low confidence classification → range quote (midpoint of price range)
- Auto-confirm threshold: <£300
- Human review range: £300–£800
- Hard block ceiling: >£800
- Replacement jobs: always escalated regardless of price
- Floor price enforced per job type; competitor price-matching declined
- New customer discount: up to 10%; returning customer discount: up to 15%; max 2 negotiation rounds
- Self-help diagnostic visit: £65 base, £55 floor; fee redeemable against repair

## Demo Scenarios (all 6 required for MVP)
- Scenario 1 (happy path): boiler repressurise, high confidence, next-day, inner London; completes in <60s; quote £95; MUST NOT CUT
- Scenario 2 (surge pricing): same job, evening/weekend; quote £142.50 (×1.5 multiplier); transparent surcharge explanation
- Scenario 3 (negotiation): minor repair £120; returning customer pushback; 15% discount offered (£102); competitor match refused; auto-confirm under £300
- Scenario 4 (gas smell hard stop): Input Guard fires before any other node; hard stop + emergency redirect; MUST NOT CUT
- Scenario 5 (scope escalation): 18-year-old boiler, replacement recommended; authority hard block >£800; human handoff messaging; escalation flag in QuoteState
- Scenario 6 (out-of-scope): Worcester Bosch brand not in config (supported: Vaillant, Baxi, Ideal); graceful decline, external redirect, no hallucinated diagnosis

## Success Criteria
- All 6 demo scenarios execute end-to-end without failure
- Scenario 1 completes <60 seconds
- Scenario 4 gas-smell hard stop fires before any pricing logic
- Scenario 6 returns graceful escalation with no hallucinated response
- LangSmith trace available and readable for every demo run
- QuoteState schema consistent across all nodes — no key errors or missing fields
- Autonomy (hackathon): full quoting loop, zero human input, 9-node conditional graph
- Technical Depth: LangGraph stateful graph, LangSmith tracing, typed state contract, cross-cutting safety
- Creativity: diagnostic-first approach; safety-first as product feature

## Functional Requirements (condensed)
- FR1–4: session start/unique ID; multi-turn state; in-session quote retrieval
- FR5: prompt injection detection and block before any processing
- FR6: gas-smell/gas-leak detection → immediate hard stop from any stage
- FR7: intent classification (greeting/quote request/general enquiry/complaint/emergency) with routing; greetings and non-quote intents keep session alive for re-classification
- FR8: safety-triggered conversations redirect to emergency services with contact info
- FR9–11: max 5-question diagnostic exchange; structured symptom extraction; terminate after 4 exchanges if needed
- FR12: symptom → job type + confidence (high/medium/low)
- FR13: validate all requests against business_config.json; decline anything outside
- FR14: boiler replacement detection → auto-escalate regardless of authority level
- FR15: range quote when confidence is medium/low
- FR16: check availability by urgency tier, return up to 3 slots
- FR17: time/day detection → urgency multiplier application
- FR18: ULEZ surcharge by postcode zone
- FR19: price = f(job type, confidence, urgency tier, postcode zone)
- FR20: parts estimate in price where applicable
- FR21–25: negotiation — floor price enforcement; new/returning customer discount tiers; competitor match refusal; value-based hold
- FR26–28: authority tiers — auto-confirm <threshold; flag for review in range; hard-block above ceiling
- FR29: strip internal fields (cost price, margin, capacity data, engineer names) from customer-facing responses
- FR30: quote with unique reference number, validity window, next steps
- FR31–33: load all rules from single config file; availability from stub + dynamic engineer scheduling; operator modifies config without code change
- FR34–35: LangSmith trace per node execution; full reasoning trace inspectable per session
- FR36 (new): returning user detection via Luffa uid + Supabase quote history; loyalty discount auto-applied
- FR37 (new): self-help flow — show DIY steps before quoting for eligible jobs; diagnostic visit offered if unresolved
- FR38 (new): postcode-deferred pricing — quote flow pauses to collect postcode before ULEZ calculation
- FR39 (new): /end command for explicit session termination; 2-minute inactivity timeout
- FR40 (new): Luffa bot integration — polling adapter with slot selection and payment flows

## Non-Functional Requirements
- NFR1: complete quote response <60s for Scenario 1 (happy path)
- NFR2: individual node execution <5s under normal conditions
- NFR3: FastAPI /api/chat response <500ms excluding LLM inference
- NFR4: LangSmith traces visible in dashboard within 10s of session completing
- NFR5: all 6 demo scenarios error-free before presentation
- NFR6: QuoteState no key errors or missing field exceptions at any node transition
- NFR7: gas-smell hard stop fires on 100% of gas-leak indicator inputs (0 false negatives)
- NFR8: 100% graceful out-of-scope escalation; 0 hallucinated responses outside configured knowledge base

## Scope Boundaries
- In: 11-node LangGraph agent; business_config.json + engineers.json; FastAPI 7-endpoint API; LangSmith tracing; Luffa bot integration; Supabase persistence; basic web frontend; Railway deployment; 6 demo scenarios
- Delivered beyond original MVP: Luffa chat channel, Supabase user persistence, dynamic engineer availability, self-help flows, postcode-deferred pricing, PII masking, returning user detection
- Out (current): multi-tenancy, real calendar/booking integration, production SaaS surfaces
- Deferred (Phase 2): multi-trades config (electrician, locksmith), email/WhatsApp channels, admin portal, human oversight mobile notifications
- Deferred (Phase 3): any-vertical deployment via config swap; continuous learning from quote outcomes

## Team & Build Plan
- Person A: LangGraph agent, all 9 nodes, diagnostic knowledge base, business logic
- Person B: FastAPI backend, data fixtures, business_config.json
- No frontend engineer needed for MVP
- Contingency cuts (in order): (1) Scenario 6 — loses ChatGPT differentiator but not core; (2) Negotiation Node simplified to fixed pricing; (3) Scenarios 1+4 — DO NOT CUT
- Build risk: lock QuoteState schema and node signatures in first 2 hours; Scenario 1 E2E is integration test; script all 6 scenarios as pre-written Postman message sequences

## Risks
- LLM answers out-of-scope questions despite config — mitigated: scope check in Job Classifier node logic, not LLM prompt
- Gas-smell detection misses paraphrased inputs — mitigated: keyword list covers sulphur/rotten eggs/gas smell/gas leak variants
- Authority limits bypassed via social engineering — mitigated: Authority Check runs after Negotiation, cannot be negotiated away
- LangGraph graph wiring time overrun — mitigated: lock schema first 2 hours
- Integration failures at hour 10 — mitigated: Scenario 1 E2E as integration test
- Demo instability on the day — mitigated: pre-scripted Postman collections for all 6 scenarios
