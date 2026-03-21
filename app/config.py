import json
import os
import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Single model used across every node. Override via LLM_MODEL env var.
_DEFAULT_MODEL = "anthropic/claude-haiku-4-5"


def get_llm(max_tokens: int = 512, temperature: float = 0) -> ChatOpenAI:
    """Return a ChatOpenAI instance routed through OpenRouter.

    The model is read from the LLM_MODEL environment variable so it can be
    changed for the whole application from one place without touching any node.
    """
    model = os.environ.get("LLM_MODEL", _DEFAULT_MODEL)
    return ChatOpenAI(
        model=model,
        openai_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        openai_api_base=OPENROUTER_BASE_URL,
        max_tokens=max_tokens,
        temperature=temperature,
    )

DATA_DIR = Path(__file__).parent.parent / "data"


@lru_cache(maxsize=1)
def load_business_config() -> Dict[str, Any]:
    with open(DATA_DIR / "business_config.json", "r") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_availability() -> Dict[str, Any]:
    with open(DATA_DIR / "availability.json", "r") as f:
        return json.load(f)


def get_ulez_zone(postcode: str) -> str:
    """
    Return 'inner', 'outer', or 'outside' for a given postcode string.

    Uses longest-prefix matching to handle both standard districts ('N1', 'E10')
    and sub-districts like 'EC1A' (which should match config entry 'EC1').

    Examples:
      'N1 2AB'  → district 'N1'  → inner
      'E10 5BJ' → district 'E10' → outer   (NOT matched by 'E1' due to longest-prefix)
      'EC1A 1BB'→ district 'EC1A'→ inner   (matched by config entry 'EC1')
    """
    config = load_business_config()
    ulez = config["ulez_zones"]

    district = postcode.strip().upper().split()[0]

    inner_set = set(ulez["inner"]["postcodes"])
    outer_set = set(ulez["outer"]["postcodes"])

    # Try increasingly shorter prefixes of the district (longest first).
    # This ensures 'E10' matches 'E10' exactly before it could match 'E1'.
    for length in range(len(district), 0, -1):
        prefix = district[:length]
        if prefix in inner_set:
            return "inner"
        if prefix in outer_set:
            return "outer"

    return "outside"


def get_ulez_surcharge(zone: str) -> float:
    config = load_business_config()
    return float(config["ulez_zones"].get(zone, {}).get("surcharge", 0))


def resolve_slot_dates(slots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Resolve 'today', 'tomorrow', and 'day_N' date placeholders to
    human-readable day + date strings (e.g. 'Monday 23 March').

    Used by both the availability node and the negotiation node so the logic
    stays in one place.
    """
    today = datetime.date.today()

    def _fmt(d: datetime.date) -> str:
        return d.strftime("%A %d %B").replace(" 0", " ")

    resolved = []
    for slot in slots:
        s = dict(slot)
        raw = s.get("date", "")
        if raw == "today":
            s["date"] = _fmt(today)
        elif raw == "tomorrow":
            s["date"] = _fmt(today + datetime.timedelta(days=1))
        elif raw.startswith("day_"):
            try:
                n = int(raw.split("_", 1)[1])
                s["date"] = _fmt(today + datetime.timedelta(days=n))
            except (ValueError, IndexError):
                pass  # leave the raw string as-is
        resolved.append(s)
    return resolved
