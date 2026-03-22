"""
Google Calendar via Civic MCP — availability queries and booking event creation.

Uses langchain-mcp-adapters (MultiServerMCPClient) to connect to Civic's MCP hub
with streamable_http transport. Tool names on the LangGraph profile:
  - google-calendar-query_freebusy  → busy periods (inverted to free slots)
  - google-calendar-create_event    → booking confirmation

Falls back gracefully — returns None/[] on any failure so the availability node
can fall through to existing static/dynamic slot generation.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
from typing import Any, Dict, List, Optional

from app.config import load_engineers

_TIMEZONE = "Europe/London"
_MIN_SLOT_DURATION = 60  # minutes — 1-hour job window
_SLOT_DURATION_HOURS = 2  # cap display slots to 2-hour windows


def _get_civic_config() -> Optional[dict]:
    """Build MultiServerMCPClient config from env vars."""
    url = os.environ.get("CIVIC_URL")
    token = os.environ.get("CIVIC_TOKEN")
    if not url or not token:
        return None
    return {
        "civic": {
            "transport": "streamable_http",
            "url": url,
            "headers": {"Authorization": f"Bearer {token}"},
        }
    }


async def _call_civic_tool(tool_name: str, arguments: dict) -> Optional[Any]:
    """Call a Civic MCP tool via MultiServerMCPClient.

    Returns the tool result content or None on failure.
    """
    config = _get_civic_config()
    if not config:
        print("[Calendar] CIVIC_URL or CIVIC_TOKEN not set")
        return None

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient(config)
        tools = await client.get_tools()

        target = None
        for t in tools:
            if t.name == tool_name:
                target = t
                break

        if not target:
            print(f"[Calendar] Tool '{tool_name}' not found in Civic MCP")
            return None

        result = await target.ainvoke(arguments)
        if isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, ValueError):
                return result
        return result

    except Exception as e:
        print(f"[Calendar] Civic MCP call failed: {e}")
        return None


def _run_async(coro):
    """Run an async coroutine from sync code, handling existing event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=30)
    else:
        return asyncio.run(coro)


def _get_time_window(urgency_tier: str) -> tuple:
    """Return (timeMin, timeMax) as RFC3339 strings for the query window."""
    now = datetime.datetime.now()
    today = now.date()

    if urgency_tier == "same_day":
        if now.hour >= 22:
            tomorrow = today + datetime.timedelta(days=1)
            return f"{tomorrow}T07:00:00Z", f"{tomorrow}T22:00:00Z"
        time_min = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        time_max = f"{today}T22:00:00Z"
    elif urgency_tier == "evening_weekend":
        time_min = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_date = today + datetime.timedelta(days=2)
        time_max = f"{end_date}T22:00:00Z"
    elif urgency_tier == "weekday_afternoon":
        time_min = f"{today + datetime.timedelta(days=1)}T12:00:00Z"
        time_max = f"{today + datetime.timedelta(days=5)}T17:00:00Z"
    else:
        # next_day
        tomorrow = today + datetime.timedelta(days=1)
        time_min = f"{tomorrow}T07:00:00Z"
        time_max = f"{tomorrow}T22:00:00Z"

    return time_min, time_max


def _parse_busy_from_text(text: str) -> List[tuple]:
    """Extract busy periods from the freebusy text response.

    Looks for lines like: "    - 2026-03-23T10:00:00Z to 2026-03-23T14:30:00Z"
    """
    import re
    pattern = re.compile(
        r"-\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?)\s+to\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?)"
    )
    busy = []
    for match in pattern.finditer(text):
        try:
            start = datetime.datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
            end = datetime.datetime.fromisoformat(match.group(2).replace("Z", "+00:00"))
            busy.append((start, end))
        except ValueError:
            continue
    return busy


def _busy_to_free(busy_periods: List[tuple], window_start: str, window_end: str) -> List[dict]:
    """Convert busy period tuples into free slots by finding gaps.

    busy_periods: [(start_dt, end_dt), ...]
    Returns: [{"start": "...", "end": "..."}, ...] — free gaps >= _MIN_SLOT_DURATION
    """
    w_start = datetime.datetime.fromisoformat(window_start.replace("Z", "+00:00"))
    w_end = datetime.datetime.fromisoformat(window_end.replace("Z", "+00:00"))

    busy = sorted(busy_periods, key=lambda x: x[0])

    free = []
    cursor = w_start
    for bs, be in busy:
        if bs > cursor:
            gap_minutes = (bs - cursor).total_seconds() / 60
            if gap_minutes >= _MIN_SLOT_DURATION:
                free.append({
                    "start": cursor.isoformat(),
                    "end": bs.isoformat(),
                })
        cursor = max(cursor, be)

    # Trailing free time
    if w_end > cursor:
        gap_minutes = (w_end - cursor).total_seconds() / 60
        if gap_minutes >= _MIN_SLOT_DURATION:
            free.append({
                "start": cursor.isoformat(),
                "end": w_end.isoformat(),
            })

    return free


def _format_slot(idx: int, free_slot: dict) -> Optional[Dict[str, Any]]:
    """Convert a free slot to FixFlow's slot format."""
    try:
        start_str = free_slot.get("start", "")
        end_str = free_slot.get("end", "")

        start_dt = datetime.datetime.fromisoformat(start_str)
        end_dt = datetime.datetime.fromisoformat(end_str)

        # Cap slot to configured duration for display
        if (end_dt - start_dt).total_seconds() > _SLOT_DURATION_HOURS * 3600:
            end_dt = start_dt + datetime.timedelta(hours=_SLOT_DURATION_HOURS)

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

    Uses query_freebusy to get busy periods, inverts to free slots.
    Returns max 3 slots in FixFlow's standard format, or [] on failure.
    """
    engineers_data = load_engineers()
    calendar_ids = list(dict.fromkeys(
        eng.get("calendar_id")
        for eng in engineers_data.get("engineers", [])
        if eng.get("calendar_id")
    ))

    if not calendar_ids:
        return []

    time_min, time_max = _get_time_window(urgency_tier)

    result = _run_async(_call_civic_tool("google-calendar-query_freebusy", {
        "time_min": time_min,
        "time_max": time_max,
        "calendar_ids": calendar_ids,
    }))

    if not result:
        return []

    # Extract busy periods from the response.
    # Civic MCP returns a list of content blocks with text descriptions.
    busy_periods = []
    if isinstance(result, list):
        for block in result:
            if isinstance(block, dict) and block.get("type") == "text":
                busy_periods.extend(_parse_busy_from_text(block.get("text", "")))
    elif isinstance(result, dict):
        calendars = result.get("calendars", {})
        for cal_data in calendars.values():
            if isinstance(cal_data, dict):
                for b in cal_data.get("busy", []):
                    try:
                        bs = datetime.datetime.fromisoformat(b["start"].replace("Z", "+00:00"))
                        be = datetime.datetime.fromisoformat(b["end"].replace("Z", "+00:00"))
                        busy_periods.append((bs, be))
                    except (ValueError, KeyError):
                        pass
    elif isinstance(result, str):
        busy_periods = _parse_busy_from_text(result)

    # Invert busy → free
    free_slots = _busy_to_free(busy_periods, time_min, time_max)

    if not free_slots:
        # No busy periods means the entire window is free
        free_slots = [{"start": time_min, "end": time_max}]

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
    calendar_id = None
    for eng in engineers_data.get("engineers", []):
        if eng.get("calendar_id"):
            calendar_id = eng["calendar_id"]
            break

    if not calendar_id:
        return None

    result = _run_async(_call_civic_tool("google-calendar-create_event", {
        "summary": summary,
        "start_time": start_rfc3339,
        "end_time": end_rfc3339,
        "calendar_id": calendar_id,
        "description": description,
        "location": location,
        "timezone": _TIMEZONE,
    }))

    if result:
        # Civic MCP returns list of content blocks
        if isinstance(result, list):
            for block in result:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if "Successfully created" in text:
                        # Extract event link as ID reference
                        print(f"[Calendar] {text[:150]}")
                        return text
        elif isinstance(result, dict):
            event_id = result.get("id") or result.get("eventId")
            if event_id:
                print(f"[Calendar] Booking event created: {event_id}")
                return event_id
        elif isinstance(result, str) and "Successfully" in result:
            print(f"[Calendar] Event created: {result[:100]}")
            return result

    print("[Calendar] Event creation returned no event ID")
    return None
