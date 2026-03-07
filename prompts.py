"""
prompts.py — Claude prompt strings for Marcus.

Note: the main system prompt is now assembled from workspace Markdown files
(AGENTS.md, SOUL.md, IDENTITY.md, USER.md, MEMORY.md) by workspace.assemble_context().
This module handles task-specific prompts only.
"""

# ── Onboarding ─────────────────────────────────────────────────────────────────

_BASICS_PARSE = """\
From this text, extract the person's name and location.
Return ONLY JSON: {{"name": "First name only, capitalised", "location": "city or country as given"}}
Text: "{text}"\
"""

_IDENTITY_MD = """\
Based on the user's onboarding answers, write the full content for their IDENTITY.md file.
Return ONLY the Markdown content — no preamble, no commentary, no code fences.

Use exactly this structure (fill every section from the answers; infer sensibly where needed):

# IDENTITY.md — {name}'s Profile

## Name
{name}

## Timezone
{timezone}

## Occupation
[from answers]

## Short-Term Goals
- [bullet per goal from answers]

## Long-Term Goals
- [bullet per goal from answers]

## Dreams
- [bullet per dream from answers]

## Values
- [bullet per value from answers]

## Interests
- [bullet per interest from answers]

## Key Context
[2-3 sentences: current situation, main challenges, personality traits — what Marcus needs to know to serve them well from day one]

---
User's name: {name}
User's timezone: {timezone}
Onboarding answers:
{answers}\
"""

# ── Scheduled proactive messages ───────────────────────────────────────────────
# Profile context comes from workspace files injected as system prompt — no args needed.

_PROACTIVE = {
    "morning": (
        "Generate a personalised morning message for the user. 3-4 sentences. "
        "One Stoic thought woven in naturally. "
        "One concrete suggestion anchored in their current goals from IDENTITY.md. "
        "Like a general greeting a soldier at dawn. Read IDENTITY.md for their name and goals."
    ),
    "midday": (
        "Generate a brief midday check-in for the user. 2-3 sentences. "
        "One pointed question about morning progress toward their goals. "
        "One practical nudge. Use their name from IDENTITY.md."
    ),
    "evening": (
        "Generate an evening message for the user. 3-4 sentences. "
        "Invite honest reflection on today's work. "
        "Ask for the single most important thing for tomorrow. "
        "Close with a Stoic thought on rest. Use their name from IDENTITY.md."
    ),
    "weekly": (
        "Generate a weekly recap for the user. 4-5 sentences. "
        "Reflect on the week against their goals in IDENTITY.md. Note a pattern observed. "
        "Ask one powerful question. Set an intention for next week."
    ),
    "monday": (
        "Generate a Monday activation message. 3-4 sentences. "
        "Energising and purposeful. Name their top priorities this week from IDENTITY.md. "
        "One Stoic line to carry as a shield."
    ),
}


def basics_parse_prompt(text: str) -> str:
    return _BASICS_PARSE.format(text=text)


def identity_md_prompt(name: str, timezone: str, answers: str) -> str:
    return _IDENTITY_MD.format(name=name, timezone=timezone, answers=answers)


def proactive_prompt(msg_type: str) -> str:
    """Prompt for scheduled proactive messages. System context comes from workspace files."""
    return _PROACTIVE.get(msg_type, _PROACTIVE["morning"])
