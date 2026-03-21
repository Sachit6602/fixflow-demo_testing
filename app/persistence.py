"""
Supabase persistence layer for user and quote history tracking.

Provides automatic returning-user detection based on Luffa uid
and quote history stored in Supabase (Postgres).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

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
) -> None:
    """Record a completed quote and increment the user's total."""
    sb = get_supabase()

    # Insert quote history
    sb.table("quote_history").insert({
        "luffa_uid": uid,
        "session_id": session_id,
        "quote_reference": quote_ref,
        "job_type": job_type,
        "final_price": final_price,
    }).execute()

    # Increment total_quotes on user
    user = sb.table("users").select("total_quotes").eq("luffa_uid", uid).execute()
    if user.data:
        new_total = user.data[0]["total_quotes"] + 1
        sb.table("users").update({
            "total_quotes": new_total,
            "last_seen": "now()",
        }).eq("luffa_uid", uid).execute()


def update_customer_name(uid: str, name: str) -> None:
    """Update the customer name when learned from conversation."""
    sb = get_supabase()
    sb.table("users").update({"customer_name": name}).eq("luffa_uid", uid).execute()
