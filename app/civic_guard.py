"""
Civic Bodyguard — prompt injection detection via Civic's HTTP API.

Bodyguard analyses prompts for injection attacks, social engineering,
and other LLM threats. Returns a threat score (0–1) and findings.

Used as the PRIMARY injection detection layer in input_guard.py.
Falls back to the existing regex + LLM layers if Bodyguard is
unreachable or unconfigured.

API docs: https://docs.civic.com/labs/private/bodyguard
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

_BODYGUARD_URL = "https://app.civic.com/bodyguard/check"
_TIMEOUT_SECONDS = 3  # keep latency tight — fallback handles failures


def _get_api_key() -> Optional[str]:
    return os.environ.get("CIVIC_KEY") or os.environ.get("CIVIC_API_KEY")


def check_injection(text: str, threshold: float = 0.5) -> Optional[Dict[str, Any]]:
    """Check a customer message for prompt injection via Civic Bodyguard.

    Returns:
        dict with keys:
            is_injection (bool)  — True if threat score exceeds threshold
            threat_score (float) — 0.0 (safe) to 1.0 (extreme risk)
            findings (list)      — details of detected threats
        None if Bodyguard is unreachable or unconfigured (triggers fallback).
    """
    api_key = _get_api_key()
    if not api_key:
        # No API key configured — signal caller to use fallback
        return None

    try:
        resp = requests.post(
            _BODYGUARD_URL,
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
            },
            json={"prompt": text},
            timeout=_TIMEOUT_SECONDS,
        )

        if resp.status_code != 200:
            # Non-200 — treat as unreachable, use fallback
            return None

        data = resp.json()
        threat_score = float(data.get("threatScore", 0.0))
        findings = data.get("findings", [])

        return {
            "is_injection": threat_score >= threshold,
            "threat_score": threat_score,
            "findings": findings,
        }

    except (requests.RequestException, ValueError, KeyError):
        # Network error, timeout, or malformed response — use fallback
        return None
