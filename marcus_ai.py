"""
marcus_ai.py — Claude API calls for Marcus. All prompts live in prompts.py.

Models:
  CHAT — claude-haiku-4-5-20251001  (reactive chat: fast, cheap)
  TASK — claude-sonnet-4-6          (proactive messages, analysis, onboarding parsing)
  DEEP — claude-opus-4-6            (user-requested only — prefix message with "deep:")
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


# ── Onboarding helpers ─────────────────────────────────────────────────────────

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


def write_identity(name: str, timezone: str, answers: str) -> str:
    """Generate IDENTITY.md Markdown from onboarding answers. Uses Sonnet."""
    return _call(
        TASK,
        [{"role": "user", "content": prompts.identity_md_prompt(name, timezone, answers)}],
        max_tokens=1000,
    )


# ── Scheduled proactive messages ───────────────────────────────────────────────

def generate_proactive(phone: str, msg_type: str) -> str:
    """Generate a scheduled proactive message using workspace context. Uses Sonnet."""
    import workspace as ws
    system = ws.assemble_context(phone)
    prompt = prompts.proactive_prompt(msg_type)
    return _call(TASK, [{"role": "user", "content": prompt}], system=system, max_tokens=350)
