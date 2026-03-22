"""
Google Calendar via Civic MCP — availability queries and booking event creation.

Uses the same Civic MCP hub HTTP pattern as civic_guard.py. Calls Google Calendar
MCP tools (gcal_find_my_free_time, gcal_create_event) through the Civic hub.

Falls back gracefully — returns None/[] on any failure so the availability node
can fall through to existing static/dynamic slot generation.
"""
from __future__ import annotations

import datetime
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import requests

from app.config import load_engineers

_CIVIC_HUB_URL = "https://app.civic.com/hub/mcp"
_TIMEOUT_SECONDS = 5
_TIMEZONE = "Europe/London"
_MIN_SLOT_DURATION = 60  # minutes — 1-hour job window


def _get_auth_token() -> Optional[str]:
    """Return Civic auth token from env. Falls back to CIVIC_API_KEY if set."""
    return os.environ.get("CIVIC_AUTH_TOKEN") or os.environ.get("CIVIC_API_KEY")


def _call_civic_calendar_tool(tool_name: str, arguments: dict) -> Optional[dict]:
    """Call a Google Calendar MCP tool via the Civic hub.

    Returns parsed JSON response or None on any failure.
    """
    token = _get_auth_token()
    if not token:
        return None

    try:
        resp = requests.post(
            _CIVIC_HUB_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            },
            timeout=_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            print(f"[Calendar] Civic hub returned {resp.status_code}")
            return None

        data = resp.json()
        # MCP responses nest the result under "result" or "content"
        return data.get("result") or data

    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"[Calendar] Civic hub call failed: {e}")
        return None


def _get_time_window(urgency_tier: str) -> tuple:
    """Return (timeMin, timeMax) as RFC3339 strings (no timezone) for the query window."""
    now = datetime.datetime.now()
    today = now.date()

    if urgency_tier == "same_day":
        # Rest of today until end of operating hours
        time_min = now.strftime("%Y-%m-%dT%H:%M:%S")
        time_max = f"{today}T22:00:00"
    elif urgency_tier == "evening_weekend":
        # Tonight + next 2 days
        time_min = now.strftime("%Y-%m-%dT%H:%M:%S")
        end_date = today + datetime.timedelta(days=2)
        time_max = f"{end_date}T22:00:00"
    elif urgency_tier == "weekday_afternoon":
        # Next 5 days, 12pm-5pm windows
        time_min = f"{today + datetime.timedelta(days=1)}T12:00:00"
        time_max = f"{today + datetime.timedelta(days=5)}T17:00:00"
    else:
        # next_day — tomorrow full day
        tomorrow = today + datetime.timedelta(days=1)
        time_min = f"{tomorrow}T07:00:00"
        time_max = f"{tomorrow}T22:00:00"

    return time_min, time_max


def _format_slot(idx: int, free_slot: dict) -> Optional[Dict[str, Any]]:
    """Convert a gcal_find_my_free_time freeSlot to FixFlow's slot format.

    Input freeSlot example:
        {"start": "2026-03-23T10:00:00+00:00", "end": "2026-03-23T12:00:00+00:00",
         "startFormatted": "Mon 23 Mar 10:00", "duration": "120"}

    Output:
        {"id": "cal_1", "date": "Monday 23 March", "time": "10:00–12:00",
         "_start_rfc3339": "...", "_end_rfc3339": "..."}
    """
    try:
        start_str = free_slot.get("start", "")
        end_str = free_slot.get("end", "")

        # Parse ISO timestamps
        start_dt = datetime.datetime.fromisoformat(start_str)
        end_dt = datetime.datetime.fromisoformat(end_str)

        # Cap slot to 2 hours max for display
        if (end_dt - start_dt).total_seconds() > 7200:
            end_dt = start_dt + datetime.timedelta(hours=2)

        date_str = start_dt.strftime("%A %d %B").replace(" 0", " ")
        time_str = f"{start_dt.strftime('%H:%M')}–{end_dt.strftime('%H:%M')}"

        return {
            "id": f"cal_{idx + 1}",
            "date": date_str,
            "time": time_str,
            "_start_rfc3339": start_dt.isoformat(),
            "_end_rfc3339": end_dt.isoformat(),
        }
    except (ValueError, TypeError, KeyError):
        return None


def find_free_slots(urgency_tier: str) -> List[Dict[str, Any]]:
    """Query Google Calendar via Civic MCP for real free slots.

    Returns max 3 slots in FixFlow's standard format, or [] on failure.
    """
    engineers_data = load_engineers()
    # Collect unique calendar IDs from engineers
    calendar_ids = list({
        eng.get("calendar_id")
        for eng in engineers_data.get("engineers", [])
        if eng.get("calendar_id")
    })

    if not calendar_ids:
        return []

    time_min, time_max = _get_time_window(urgency_tier)

    result = _call_civic_calendar_tool("gcal_find_my_free_time", {
        "calendarIds": calendar_ids,
        "timeMin": time_min,
        "timeMax": time_max,
        "timeZone": _TIMEZONE,
        "minDuration": _MIN_SLOT_DURATION,
    })

    if not result:
        return []

    # Parse free slots from response
    free_slots = result.get("freeSlots", [])
    if not free_slots:
        return []

    # Convert to FixFlow format, limit to 3
    formatted = []
    for i, fs in enumerate(free_slots):
        slot = _format_slot(i, fs)
        if slot:
            formatted.append(slot)
        if len(formatted) >= 3:
            break

    return formatted


def create_booking_event(
    summary: str,
    start_rfc3339: str,
    end_rfc3339: str,
    description: str,
    location: str,
) -> Optional[str]:
    """Create a booking event on Google Calendar via Civic MCP.

    Returns event ID on success, None on failure.
    Failure does NOT block booking confirmation.
    """
    engineers_data = load_engineers()
    # Use first engineer's calendar_id for the booking
    calendar_id = None
    for eng in engineers_data.get("engineers", []):
        if eng.get("calendar_id"):
            calendar_id = eng["calendar_id"]
            break

    if not calendar_id:
        return None

    result = _call_civic_calendar_tool("gcal_create_event", {
        "calendarId": calendar_id,
        "event": {
            "summary": summary,
            "start": {
                "dateTime": start_rfc3339,
                "timeZone": _TIMEZONE,
            },
            "end": {
                "dateTime": end_rfc3339,
                "timeZone": _TIMEZONE,
            },
            "description": description,
            "location": location,
        },
        "sendUpdates": "none",
    })

    if result:
        # Try to extract event ID from response
        event_id = result.get("id") or result.get("eventId")
        if event_id:
            print(f"[Calendar] Booking event created: {event_id}")
            return event_id

    print("[Calendar] Event creation returned no event ID")
    return None
