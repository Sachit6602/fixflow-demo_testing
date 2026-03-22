"""
Supabase persistence layer for user tracking, quote history,
chat sessions, and event logging.

Powers the business dashboard with real-time data capture.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from supabase import create_client, Client

_client: Optional[Client] = None


def get_supabase() -> Client:
    """Return a singleton Supabase client."""
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        _client = create_client(url, key)
    return _client


def get_or_create_user(uid: str, customer_name: str = "Customer") -> Dict[str, Any]:
    """Upsert a user record and return it."""
    sb = get_supabase()

    # Try to fetch existing user
    result = sb.table("users").select("*").eq("luffa_uid", uid).execute()

    if result.data:
        # Update last_seen
        sb.table("users").update({"last_seen": "now()"}).eq("luffa_uid", uid).execute()
        return result.data[0]

    # Create new user
    new_user = {
        "luffa_uid": uid,
        "customer_name": customer_name,
    }
    result = sb.table("users").insert(new_user).execute()
    return result.data[0]


def is_returning_user(uid: str) -> bool:
    """Check if a user has completed at least one quote."""
    sb = get_supabase()
    result = sb.table("users").select("total_quotes").eq("luffa_uid", uid).execute()

    if not result.data:
        return False
    return result.data[0]["total_quotes"] > 0


def record_quote(
    uid: str,
    session_id: str,
    quote_ref: str,
    job_type: Optional[str],
    final_price: Optional[float],
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Record a completed quote and increment the user's total."""
    sb = get_supabase()

    row = {
        "luffa_uid": uid,
        "session_id": session_id,
        "quote_reference": quote_ref,
        "job_type": job_type,
        "final_price": final_price,
    }
    if extra:
        row.update(extra)

    sb.table("quote_history").insert(row).execute()

    # Increment total_quotes on user
    user = sb.table("users").select("total_quotes").eq("luffa_uid", uid).execute()
    if user.data:
        new_total = user.data[0]["total_quotes"] + 1
        sb.table("users").update({
            "total_quotes": new_total,
            "last_seen": "now()",
        }).eq("luffa_uid", uid).execute()


def mark_quote_accepted(quote_ref: str, paid_amount: float, tx_ref: str) -> None:
    """Mark a quote as accepted and paid."""
    sb = get_supabase()
    sb.table("quote_history").update({
        "accepted": True,
        "paid_amount": paid_amount,
        "tx_ref": tx_ref,
    }).eq("quote_reference", quote_ref).execute()


def update_customer_name(uid: str, name: str) -> None:
    """Update the customer name when learned from conversation."""
    sb = get_supabase()
    sb.table("users").update({"customer_name": name}).eq("luffa_uid", uid).execute()


# ── Chat session tracking ────────────────────────────────────────────────────

def create_chat(session_id: str, luffa_uid: Optional[str] = None,
                customer_name: str = "Customer", customer_type: str = "new") -> None:
    """Record a new chat session."""
    sb = get_supabase()
    sb.table("chats").insert({
        "session_id": session_id,
        "luffa_uid": luffa_uid,
        "customer_name": customer_name,
        "customer_type": customer_type,
    }).execute()


def update_chat(session_id: str, updates: Dict[str, Any]) -> None:
    """Update a chat session with new data."""
    sb = get_supabase()
    sb.table("chats").update(updates).eq("session_id", session_id).execute()


# ── Event logging ────────────────────────────────────────────────────────────

def log_event(session_id: str, event_type: str,
              detail: Optional[Dict[str, Any]] = None,
              luffa_uid: Optional[str] = None) -> None:
    """Log a dashboard event."""
    sb = get_supabase()
    sb.table("events").insert({
        "session_id": session_id,
        "luffa_uid": luffa_uid,
        "event_type": event_type,
        "detail": json.dumps(detail or {}),
    }).execute()
