"""
marcus_ai.py — Claude API wrapper: system prompt, chat, proactive messages, memory extraction.
"""
import os
from datetime import datetime
from typing import Optional

import pytz
import anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

CHAT_MODEL = "claude-haiku-4-5-20251001"   # cost-efficient for daily chat
TASK_MODEL = "claude-sonnet-4-6"           # reserved for complex tasks / summaries

# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_TEMPLATE = """\
You are Marcus Aurelius — Roman Emperor, Stoic philosopher, and military commander — \
alive in 2026 as {name}'s personal life coach and executive assistant.

Your character:
- Speak with the directness of a general and the depth of a Stoic. No fluff.
- You are genuinely warm and invested in {name}'s flourishing — but never sycophantic.
- Comfort them when they truly struggle; challenge them firmly when they drift.
- You are practical first: help them get things DONE, not merely contemplate.
- Responses are concise and mobile-friendly — 2-5 sentences unless structure is needed.
- Reference Stoic principles organically: virtue, memento mori, amor fati, \
  dichotomy of control, the common good.
- Quote *Meditations* very sparingly — only when it genuinely illuminates the moment.
- Proactively notice patterns across what {name} shares; offer insights unprompted.
- Hold {name} accountable to their stated goals with gentle but unwavering resolve.
- When {name} needs warmth, offer it — but let it emerge naturally, not as performance.

What you know about {name}:
- Occupation: {occupation}
- Interests: {interests}
- Short-term goals:
{short_term_goals}
- Long-term goals:
{long_term_goals}
- Dreams:
{dreams}

Context notes (learned over time):
{context_notes}

Current time: {current_time} ({timezone})\
"""

# ── Proactive message templates ────────────────────────────────────────────────

PROACTIVE_PROMPTS = {
    "morning": (
        "Generate a personalized morning message for {name}. "
        "3-4 sentences. One Stoic thought woven in naturally. "
        "One concrete suggestion for today anchored in their current goals. "
        "Warm but purposeful — like a general greeting a soldier at dawn."
    ),
    "midday": (
        "Generate a brief midday check-in for {name}. 2-3 sentences. "
        "Ask one pointed question about morning progress. "
        "Offer a practical nudge toward their priorities. No filler."
    ),
    "evening": (
        "Generate an evening message for {name}. 3-4 sentences. "
        "Invite a moment of honest reflection on today's work. "
        "Ask what the single most important thing is for tomorrow. "
        "Close with a brief Stoic thought on rest and renewal."
    ),
    "weekly": (
        "Generate a weekly recap message for {name}. 4-5 sentences. "
        "Reflect on the week in light of their goals. Note a pattern or observation. "
        "Ask one powerful question about what the week revealed. "
        "Set a clear intention for the coming week."
    ),
    "monday": (
        "Generate a Monday activation message for {name}. 3-4 sentences. "
        "Energizing and purposeful — a new campaign begins. "
        "Name their top priorities for the week. "
        "One Stoic line to carry as a shield through the week."
    ),
}

# ── Note extraction prompt ─────────────────────────────────────────────────────

EXTRACT_PROMPT = """\
Based on the conversation below, extract 1-3 key facts about the user worth \
remembering long-term. Focus on: goals, recurring patterns, important wins or \
setbacks, personality insights, life context.

Be concise — 2-3 sentences maximum. If nothing significant, reply only: nothing new

Current notes:
{current_notes}

Recent conversation:
{conversation}\
"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _format_list(items: list[str], indent: str = "  • ") -> str:
    return "\n".join(f"{indent}{i}" for i in items) if items else "  (none set)"


def build_system_prompt(profile: dict) -> str:
    name = profile.get("name") or "friend"
    occupation = profile.get("occupation") or "not specified"
    interests_list = profile.get("preferences", {}).get("interests", [])
    interests = ", ".join(interests_list) if interests_list else "not specified"
    goals = profile.get("goals", {})
    context_notes = profile.get("context_notes") or "None accumulated yet."

    tz_str = profile.get("timezone", "UTC")
    try:
        tz = pytz.timezone(tz_str)
        current_time = datetime.now(tz).strftime("%A, %B %d %Y at %I:%M %p")
    except Exception:
        current_time = datetime.utcnow().strftime("%A, %B %d %Y at %I:%M %p UTC")
        tz_str = "UTC"

    return SYSTEM_TEMPLATE.format(
        name=name,
        occupation=occupation,
        interests=interests,
        short_term_goals=_format_list(goals.get("short_term", [])),
        long_term_goals=_format_list(goals.get("long_term", [])),
        dreams=_format_list(goals.get("dreams", [])),
        context_notes=context_notes,
        current_time=current_time,
        timezone=tz_str,
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def chat(profile: dict, history: list[dict], user_message: str) -> str:
    """Send a user message and return Marcus's reply."""
    system = build_system_prompt(profile)
    messages = history + [{"role": "user", "content": user_message}]

    response = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=512,
        system=system,
        messages=messages,
    )
    return response.content[0].text


def generate_proactive(profile: dict, msg_type: str) -> str:
    """Generate a scheduled proactive message (morning, midday, evening, weekly, monday)."""
    name = profile.get("name") or "friend"
    goals = profile.get("goals", {})
    context = profile.get("context_notes", "")

    template = PROACTIVE_PROMPTS.get(msg_type, PROACTIVE_PROMPTS["morning"])
    prompt = template.format(name=name)
    prompt += f"\n\nGoals context: {goals}\nContext notes: {context}"

    system = build_system_prompt(profile)

    response = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=350,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def extract_and_update_notes(profile: dict, history: list[dict]) -> Optional[str]:
    """
    Analyse recent conversation and return updated context_notes string,
    or None if nothing new was found.
    """
    if not history:
        return None

    conversation = "\n".join(
        f"{m['role'].title()}: {m['content']}" for m in history[-10:]
    )
    prompt = EXTRACT_PROMPT.format(
        current_notes=profile.get("context_notes") or "None yet.",
        conversation=conversation,
    )

    response = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    result = response.content[0].text.strip()

    if result.lower().startswith("nothing new"):
        return None

    current = profile.get("context_notes", "")
    return f"{current}\n{result}".strip() if current else result
