"""
Luffa Bot Adapter for FixFlow.

Polls the Luffa messaging API for incoming messages and routes them
through FixFlow's REST API (/api/session/start, /api/chat).

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

load_dotenv()

LUFFA_SECRET = os.environ["LUFFA_SECRET"]
LUFFA_BASE = "https://apibot.luffa.im"
FIXFLOW_BASE = os.environ.get("FIXFLOW_BASE_URL", "http://localhost:8000")

# uid -> session_id mapping (in-memory, lost on restart)
active_sessions: dict[str, str] = {}

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

    # Create a new FixFlow session
    resp = requests.post(
        f"{FIXFLOW_BASE}/api/session/start",
        json={"customer_name": "Customer", "is_returning": False},
    )
    resp.raise_for_status()
    data = resp.json()

    session_id = data["session_id"]
    active_sessions[uid] = session_id

    # Send the welcome message to the user
    send_message(uid, data["message"])
    print(f"[FixFlow] Session created for {uid}: {session_id}")
    return session_id


def handle_text_message(uid: str, text: str):
    """Forward a user message to FixFlow and relay the response back via Luffa."""
    session_id = ensure_session(uid)

    resp = requests.post(
        f"{FIXFLOW_BASE}/api/chat",
        json={"session_id": session_id, "message": text},
    )

    if resp.ok:
        data = resp.json()
        reply = data["response"]
        if data.get("quote_reference"):
            reply += f"\n\nQuote Ref: {data['quote_reference']}"
        send_message(uid, reply)
    else:
        print(f"[FixFlow] Error {resp.status_code}: {resp.text}")
        send_message(uid, "Sorry, something went wrong. Please try again.")


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
