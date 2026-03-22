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
from pathlib import Path

import requests
from dotenv import load_dotenv

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from payment import get_payment_message, handle_payment_confirmation

load_dotenv()

LUFFA_SECRET = os.environ["LUFFA_SECRET"]
LUFFA_BASE = "https://apibot.luffa.im"
FIXFLOW_BASE = os.environ.get("FIXFLOW_BASE_URL", "http://localhost:8000")
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
    return session_id


def handle_text_message(uid: str, text: str):
    """Forward a user message to FixFlow and relay the response back via Luffa."""
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
        quote_ref = data.get("quote_reference")

        if quote_ref:
            reply += f"\n\nQuote Ref: {quote_ref}"

        send_message(uid, reply)

        # If a quote was just issued, wait for slot selection
        if quote_ref and data.get("phase") == "quoting":
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

    if stripped == "1":
        response = handle_payment_confirmation(uid, BUSINESS_NAME, payment["final_price"])
        send_message(uid, response)

        # Dashboard: mark quote as accepted and paid
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from app.persistence import mark_quote_accepted, log_event
            tx_ref = response.split("Transaction: ")[1].split("\n")[0] if "Transaction:" in response else None
            mark_quote_accepted(payment["quote_ref"], payment["final_price"], tx_ref)
            # Find session_id for this uid
            sid = active_sessions.get(uid)
            if sid:
                log_event(sid, "quote_accepted", {"quote_ref": payment["quote_ref"], "slot": payment.get("slot")}, uid)
                log_event(sid, "payment_confirmed", {"quote_ref": payment["quote_ref"], "amount": payment["final_price"], "tx_ref": tx_ref}, uid)
        except Exception as e:
            print(f"[Dashboard] Payment capture failed: {e}")

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


if __name__ == "__main__":
    print(f"[Luffa Bot] Starting — polling {LUFFA_BASE}")
    print(f"[Luffa Bot] FixFlow API at {FIXFLOW_BASE}")

    while True:
        try:
            data = get_messages()
            process(data)
        except KeyboardInterrupt:
            print("\n[Luffa Bot] Shutting down.")
            break
        except Exception as e:
            print(f"[Luffa Bot] Error: {e}")
        time.sleep(1)
