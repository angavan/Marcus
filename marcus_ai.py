"""
marcus_ai.py — Claude API calls for Marcus. All prompts live in prompts.py.

Models:
  CHAT — claude-haiku-4-5-20251001  (reactive chat: fast, cheap)
  TASK — claude-sonnet-4-6          (proactive messages, analysis, extraction)
  DEEP — claude-opus-4-6            (user-requested only)
"""
import json
import os
import re
from typing import Optional

import anthropic
import pytz

import prompts

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

CHAT = "claude-haiku-4-5-20251001"
TASK = "claude-sonnet-4-6"
DEEP = "claude-opus-4-6"


def _call(model: str, messages: list[dict], system: str = "", max_tokens: int = 512) -> str:
    kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=messages)
    if system:
        kwargs["system"] = system
    return client.messages.create(**kwargs).content[0].text.strip()


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return {}


# ── Public API ─────────────────────────────────────────────────────────────────

def chat(profile: dict, history: list[dict], user_message: str, *, deep: bool = False) -> str:
    """Reactive chat. Uses Haiku by default; Opus when deep=True."""
    model = DEEP if deep else CHAT
    return _call(
        model,
        history + [{"role": "user", "content": user_message}],
        system=prompts.build_system(profile),
    )


def generate_proactive(profile: dict, msg_type: str) -> str:
    """Scheduled proactive message (morning/midday/evening/weekly/monday). Uses Sonnet."""
    return _call(
        TASK,
        [{"role": "user", "content": prompts.proactive_prompt(profile, msg_type)}],
        system=prompts.build_system(profile),
        max_tokens=350,
    )


def extract_notes(profile: dict, history: list[dict]) -> Optional[str]:
    """Extract long-term learnings from recent history. Uses Sonnet. Returns updated notes or None."""
    if not history:
        return None
    result = _call(
        TASK,
        [{"role": "user", "content": prompts.extract_prompt(profile, history)}],
        max_tokens=200,
    )
    if result.lower().startswith("nothing new"):
        return None
    current = profile.get("context_notes", "")
    return f"{current}\n{result}".strip() if current else result


def parse_intake(answers: str) -> dict:
    """Parse free-form onboarding answers into a structured profile dict. Uses Sonnet."""
    result = _call(
        TASK,
        [{"role": "user", "content": prompts.intake_parse_prompt(answers)}],
        max_tokens=800,
    )
    return _parse_json(result)


def parse_basics(text: str) -> dict:
    """Extract name and location from natural text like 'John, New York'. Uses Haiku."""
    result = _call(
        CHAT,
        [{"role": "user", "content": prompts.basics_parse_prompt(text)}],
        max_tokens=60,
    )
    return _parse_json(result)


def resolve_timezone(location: str) -> str:
    """Resolve a city/country name to a valid pytz timezone string. Uses Haiku."""
    if location.strip() in pytz.all_timezones:
        return location.strip()
    result = _call(
        CHAT,
        [{"role": "user", "content": (
            f'Return only the pytz timezone string for: "{location}". '
            "E.g. America/New_York. ONLY the string, nothing else."
        )}],
        max_tokens=30,
    )
    tz = result.strip()
    return tz if tz in pytz.all_timezones else "UTC"
