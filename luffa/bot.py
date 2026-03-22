"""
Luffa Bot Adapter for FixFlow.

Polls the Luffa messaging API for incoming messages and routes them
through FixFlow's REST API (/api/session/start-luffa, /api/chat).
Returning users are auto-detected via Supabase quote history.

Usage:
    1. Start FixFlow:  uvicorn app.main:app --reload
    2. Run this bot:   python luffa_bot.py

Env vars:
    LUFFA_SECRET       — Luffa bot authentication secret (required)
    FIXFLOW_BASE_URL   — FixFlow API base URL (default: http://localhost:8000)
"""
import json
import os
import time

import requests
from dotenv import load_dotenv

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from payment import get_payment_message, handle_payment_confirmation

load_dotenv()

LUFFA_SECRET = os.environ["LUFFA_SECRET"]
LUFFA_BASE = "https://apibot.luffa.im"
# On Railway, PORT is set by the platform. Bot runs in-process, so use localhost.
_port = os.environ.get("PORT", "8000")
FIXFLOW_BASE = os.environ.get("FIXFLOW_BASE_URL", f"http://localhost:{_port}")
BUSINESS_NAME = "FixFlow Plumbing"

# uid -> session_id mapping (in-memory, lost on restart)
active_sessions: dict[str, str] = {}

# uid -> quote info for users who need to select a slot
# { "quote_ref": str, "final_price": float }
pending_slot_selection: dict[str, dict] = {}

# uid -> payment info for users awaiting payment confirmation
# { "quote_ref": str, "final_price": float, "slot": str }
pending_payments: dict[str, dict] = {}

# Deduplication: track processed message IDs
seen_ids: set[str] = set()

# uid -> last activity timestamp (for inactivity timeout)
last_activity: dict[str, float] = {}
SESSION_TIMEOUT_SECS = 120  # 2 minutes


def clear_session(uid: str):
    """Remove all in-memory state for a uid so next message starts fresh."""
    active_sessions.pop(uid, None)
    pending_slot_selection.pop(uid, None)
    pending_payments.pop(uid, None)
    last_activity.pop(uid, None)
    print(f"[Session] Cleared for {uid}")


def check_timeouts():
    """Send timeout message and clear sessions inactive for >2 minutes."""
    now = time.time()
    timed_out = [
        uid for uid, ts in last_activity.items()
        if now - ts > SESSION_TIMEOUT_SECS
    ]
    for uid in timed_out:
        send_message(uid, (
            "It looks like you've been away for a bit — this session has timed out. "
            "Send a new message anytime to start a fresh conversation!"
        ))
        clear_session(uid)


def get_messages() -> list:
    """Poll Luffa for new incoming messages."""
    r = requests.post(f"{LUFFA_BASE}/robot/receive", json={"secret": LUFFA_SECRET})
    return r.json() if r.ok else []


def send_message(uid: str, text: str):
    """Send a text message to a Luffa user."""
    r = requests.post(
        f"{LUFFA_BASE}/robot/send",
        json={
            "secret": LUFFA_SECRET,
            "uid": uid,
            "msg": json.dumps({"text": text}),
        },
    )
    print(f"[Luffa] Sent to {uid}: {r.status_code}")


def ensure_session(uid: str) -> str:
    """Get or create a FixFlow session for this Luffa user."""
    if uid in active_sessions:
        return active_sessions[uid]

    # Check if server already has an active session for this uid
    lookup = requests.get(f"{FIXFLOW_BASE}/api/session/lookup", params={"luffa_uid": uid})
    if lookup.ok:
        session_id = lookup.json()["session_id"]
        active_sessions[uid] = session_id
        print(f"[FixFlow] Resumed session for {uid}: {session_id}")
        return session_id

    # Create a new FixFlow session with uid-based returning user detection
    resp = requests.post(
        f"{FIXFLOW_BASE}/api/session/start-luffa",
        json={"luffa_uid": uid, "customer_name": "Customer"},
    )
    resp.raise_for_status()
    data = resp.json()

    session_id = data["session_id"]
    active_sessions[uid] = session_id

    status = "returning" if data["is_returning"] else "new"
    print(f"[FixFlow] Session created for {uid} ({status}): {session_id}")

    # Send the welcome message to the user
    send_message(uid, data["message"])
    last_activity[uid] = time.time()
    return session_id


def handle_text_message(uid: str, text: str):
    """Forward a user message to FixFlow and relay the response back via Luffa."""
    last_activity[uid] = time.time()

    # Check if user is responding to a payment prompt
    if uid in pending_payments:
        handle_payment_response(uid, text)
        return

    # Check if user is selecting a time slot
    if uid in pending_slot_selection:
        handle_slot_selection(uid, text)
        return

    session_id = ensure_session(uid)

    resp = requests.post(
        f"{FIXFLOW_BASE}/api/chat",
        json={"session_id": session_id, "message": text},
    )

    if resp.ok:
        data = resp.json()
        reply = data["response"]
        phase = data.get("phase")
        quote_ref = data.get("quote_reference")

        if quote_ref:
            reply += f"\n\nQuote Ref: {quote_ref}"

        send_message(uid, reply)

        # Session ended (/end command, safety hard-stop, etc.) — clear so next msg starts fresh
        if phase == "ended":
            clear_session(uid)
            return

        # If a quote was just issued, wait for slot selection
        if quote_ref and phase == "quoting":
            quotes_resp = requests.get(
                f"{FIXFLOW_BASE}/api/quotes",
                params={"session_id": session_id},
            )
            if quotes_resp.ok:
                quotes = quotes_resp.json().get("quotes", [])
                matching = [q for q in quotes if q["reference"] == quote_ref]
                if matching and matching[0].get("final_price"):
                    pending_slot_selection[uid] = {
                        "quote_ref": quote_ref,
                        "final_price": matching[0]["final_price"],
                    }
                    print(f"[Booking] Awaiting slot selection from {uid}")
    else:
        print(f"[FixFlow] Error {resp.status_code}: {resp.text}")
        send_message(uid, "Sorry, something went wrong. Please try again.")


def handle_slot_selection(uid: str, text: str):
    """Handle a user's slot selection after receiving a quote."""
    stripped = text.strip()
    quote_info = pending_slot_selection[uid]

    # If the user sends something clearly not a slot number, exit slot selection
    # and forward to the agent as a normal message
    if stripped not in ("1", "2", "3") and len(stripped) > 1:
        del pending_slot_selection[uid]
        print(f"[Booking] {uid} exited slot selection with: {repr(text)}")
        # Re-process as a normal message
        session_id = ensure_session(uid)
        resp = requests.post(
            f"{FIXFLOW_BASE}/api/chat",
            json={"session_id": session_id, "message": text},
        )
        if resp.ok:
            data = resp.json()
            reply = data["response"]
            if data.get("phase") == "ended":
                clear_session(uid)
            send_message(uid, reply)
        else:
            send_message(uid, "Sorry, something went wrong. Please try again.")
        return

    if stripped in ("1", "2", "3"):
        slot_label = {
            "1": "Slot 1",
            "2": "Slot 2",
            "3": "Slot 3",
        }[stripped]

        send_message(uid, f"{slot_label} confirmed.")

        # Move to payment
        payment_msg = get_payment_message(quote_info["quote_ref"], quote_info["final_price"])
        pending_payments[uid] = {
            "quote_ref": quote_info["quote_ref"],
            "final_price": quote_info["final_price"],
            "slot": slot_label,
        }
        del pending_slot_selection[uid]
        send_message(uid, payment_msg["text"])
        print(f"[Booking] {uid} selected {slot_label}, payment prompt sent")
    else:
        send_message(uid, "Please reply with your preferred slot number (1, 2, or 3).")


def handle_payment_response(uid: str, text: str):
    """Handle a user's response to a payment prompt."""
    payment = pending_payments[uid]
    stripped = text.strip()

    # If the user sends something clearly not a payment response, exit payment flow
    if stripped not in ("1", "2") and len(stripped) > 1:
        del pending_payments[uid]
        clear_session(uid)
        print(f"[Payment] {uid} exited payment flow with: {repr(text)}")
        # Start fresh — forward as new conversation
        handle_text_message(uid, text)
        return

    if stripped == "1":
        response = handle_payment_confirmation(uid, BUSINESS_NAME, payment["final_price"])
        send_message(uid, response)
        # Clear payment state and session so next message starts fresh
        del pending_payments[uid]
        active_sessions.pop(uid, None)
        print(f"[Payment] Confirmed for {uid}: £{payment['final_price']:.2f}")
    elif stripped == "2":
        send_message(uid, "Booking cancelled. Your quote is still valid for 24 hours if you change your mind.")
        del pending_payments[uid]
        print(f"[Payment] Cancelled by {uid}")
    else:
        send_message(uid, "Please reply with:\n1 - Confirm & Pay\n2 - Cancel")
        print(f"[Payment] Invalid response from {uid}: {repr(text)}")


def process(data):
    """Process incoming Luffa messages."""
    if not isinstance(data, list):
        return

    for conversation in data:
        uid = conversation.get("uid")
        msg_type = conversation.get("type")

        for raw in conversation.get("message", []):
            msg = json.loads(raw)
            msg_id = msg.get("msgId")

            if msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)

            text = msg.get("text", "")
            print(f"[Luffa] Message from {uid}: {repr(text)}")

            # Only handle regular conversation messages (type "0")
            if str(msg_type) == "0" and text.strip():
                handle_text_message(uid, text)


def main_loop():
    """Main polling loop — can be run standalone or as a background thread."""
    print(f"[Luffa Bot] Starting — polling {LUFFA_BASE}")
    print(f"[Luffa Bot] FixFlow API at {FIXFLOW_BASE}")

    while True:
        try:
            data = get_messages()
            process(data)
            check_timeouts()
        except KeyboardInterrupt:
            print("\n[Luffa Bot] Shutting down.")
            break
        except Exception as e:
            print(f"[Luffa Bot] Error: {e}")
        time.sleep(1)


if __name__ == "__main__":
    main_loop()
