"""
menu.py — WhatsApp message routing and menu state machine.

Identity and memory live in workspace files. Session state (menu nav, schedule) is in SQLite.

Onboarding states:
  setup:basics    → name + location (one message)
  setup:intake    → 5 deep questions answered freely (one message)
  setup:confirm   → show parsed IDENTITY.md preview, await confirmation

Menu states:
  main            → main menu
  goals:main      → goals submenu
  goals:add_text  → waiting for goal text
  goals:add_type  → waiting for category (1/2/3)
  goals:add_dream → waiting for dream text
  goals:remove    → waiting for number to remove
  schedule:main   → schedule submenu
  schedule:edit_times → waiting for time slot selection
  schedule:set_time   → waiting for HH:MM
  settings:main   → settings submenu
  settings:name   → new name
  settings:timezone → new timezone
  settings:occupation → occupation
  settings:interests → interests list
"""
import logging
import re

import agent
import marcus_ai
import memory
import scheduler as sched
import workspace as ws

logger = logging.getLogger(__name__)

# ── Menu text ──────────────────────────────────────────────────────────────────

MAIN_MENU = """\
📜 *MARCUS*
━━━━━━━━━━━━━━━━━━━━
*1* — Chat freely
*2* — My Goals & Dreams
*3* — My Profile
*4* — Scheduled Messages
*5* — Settings

_Or just type anything to talk to me._\
"""

GOALS_MENU = """\
📜 *Goals & Dreams*
━━━━━━━━━━━━━━━━━━━━
*1* — View my goals
*2* — Add a goal
*3* — Remove a goal
*4* — Add a dream
*0* — Back\
"""

SCHEDULE_MENU = """\
📜 *Scheduled Messages*
━━━━━━━━━━━━━━━━━━━━
*1* — View current schedule
*2* — Toggle morning message
*3* — Toggle midday check-in
*4* — Toggle evening planning
*5* — Toggle weekly recap
*6* — Toggle Monday update
*7* — Change message times
*0* — Back\
"""

SETTINGS_MENU = """\
📜 *Settings*
━━━━━━━━━━━━━━━━━━━━
*1* — Update name
*2* — Update timezone
*3* — Update occupation
*4* — Update interests
*0* — Back\
"""

GOAL_TYPE_PROMPT = """\
What type of goal is this?
*1* — Short-term (weeks/months)
*2* — Long-term (years)
*3* — Dream (life aspiration)\
"""

HELP_TEXT = """\
📜 *MARCUS — Help*

Type *menu* anytime — main menu.
Type *help* — this message.
Prefix with *deep:* — use Opus for that message.

What I do:
• Chat and remember context across conversations
• Track your goals, dreams, and values (stored in your workspace files)
• Daily check-ins: morning, midday, evening
• Weekly recaps and Monday activations
• Heartbeat every 30 min — I reach out if something needs attention
• Proactively write memory after every meaningful exchange

I am not a chatbot. I am your ally.\
"""

ONBOARDING_WELCOME = """\
📜 *I am Marcus.*
Not a ghost — the spirit of two millennia of hard-won wisdom, put to work in your service.

I will be your life coach, strategist, and executive assistant. I will remember what matters, \
check in daily, and hold you accountable to your highest ambitions.

First: *what's your name, and where in the world are you?*
_(e.g. "John, New York" or "Maria in London")_\
"""

INTAKE_QUESTIONS = """\
Good, *{name}*.

Now — answer these as openly as you can. This is how I build my first picture of you.

*1.* What do you do? (work, business, study — briefly)
*2.* What are your current goals — the ones you think about most?
*3.* What are your deeper dreams or long-term ambitions?
*4.* What are your biggest current challenges or obstacles?
*5.* What do you value most in life? What principles guide you?

Write freely. I'll build your profile from what you give me.\
"""

_CONFIRM_YES = {
    "yes", "looks good", "good", "correct", "ok", "done",
    "perfect", "yep", "right", "confirmed", "accurate", "all good",
}


# ── Entry point ────────────────────────────────────────────────────────────────

def handle_message(phone: str, text: str) -> str:
    text = text.strip()
    lower = text.lower()

    session = memory.get_session(phone)
    if not session or ws.is_new_user(phone):
        if not session:
            memory.create_session(phone)
        ws.initialize_workspace(phone)
        memory.set_menu_state(phone, "setup:basics")
        return ONBOARDING_WELCOME

    menu_state = session.get("menu_state")

    # Global shortcuts
    if lower in ("menu", "home", "start"):
        memory.set_menu_state(phone, "main")
        return MAIN_MENU
    if lower in ("help", "?"):
        return HELP_TEXT

    if menu_state and menu_state.startswith("setup:"):
        return _handle_setup(phone, session, text)
    if menu_state:
        return _handle_menu_nav(phone, session, text)

    return _handle_chat(phone, text)


# ── Onboarding ─────────────────────────────────────────────────────────────────

def _handle_setup(phone: str, session: dict, text: str) -> str:
    state = session["menu_state"]
    data = session.get("menu_state_data") or {}

    if state == "setup:basics":
        parsed = marcus_ai.parse_basics(text)
        words = text.strip().split()
        fallback_name = words[0] if words else "friend"
        name = parsed.get("name", fallback_name).capitalize() or "friend"
        tz = marcus_ai.resolve_timezone(parsed.get("location", text))
        tz_note = f"\n_(Timezone set to {tz} — you can change this in Settings if needed.)_" if tz == "UTC" else ""
        memory.set_menu_state(phone, "setup:intake", {"name": name, "timezone": tz})
        return INTAKE_QUESTIONS.format(name=name) + tz_note

    if state == "setup:intake":
        name = data.get("name", "friend")
        tz = data.get("timezone", "UTC")
        identity_content = marcus_ai.write_identity(name, tz, text)
        ws.write_file(phone, "IDENTITY.md", identity_content)
        # Update USER.md timezone
        user_md = ws.read_file(phone, "USER.md")
        ws.write_file(phone, "USER.md", user_md.replace("[To be filled during onboarding]", tz))
        memory.set_menu_state(phone, "setup:confirm", {"intake_text": text})
        preview = ws.to_whatsapp(identity_content)
        return f"📜 *Here's my first picture of you:*\n\n{preview}\n\nDoes this capture you accurately? Say *\"looks good\"* or correct what I missed."

    if state == "setup:confirm":
        if any(w in text.lower() for w in _CONFIRM_YES) or text.lower() in _CONFIRM_YES:
            memory.set_menu_state(phone, None)
            try:
                sched.schedule_user(phone, session["schedule"])
            except Exception:
                logger.warning("Failed to schedule jobs for %s after onboarding", phone)
            identity = ws.read_file(phone, "IDENTITY.md")
            name = _extract_name(identity)
            return (
                f"📜 *Workspace saved, {name}.*\n\n"
                "Your identity, goals, and values live in editable Markdown files. "
                "Marcus will read and update them as you grow.\n\n"
                "I'll reach out each morning, midday, and evening — "
                "and every 30 minutes I'll check if something deserves your attention.\n\n"
                f"The work begins now, {name}."
            )
        # Corrections: re-generate IDENTITY.md with the correction context
        original = data.get("intake_text", "")
        corrected = marcus_ai.write_identity(
            _extract_name(ws.read_file(phone, "IDENTITY.md")),
            ws.get_timezone(phone),
            f"Original answers:\n{original}\n\nUser correction: {text}",
        )
        ws.write_file(phone, "IDENTITY.md", corrected)
        memory.set_menu_state(phone, "setup:confirm", {"intake_text": original})
        preview = ws.to_whatsapp(corrected)
        return f"✓ Updated.\n\n{preview}\n\nDoes this look right now?"

    return "Something went wrong. Type *menu* to reset."


# ── Menu navigation ────────────────────────────────────────────────────────────

def _handle_menu_nav(phone: str, session: dict, text: str) -> str:
    state = session["menu_state"]
    data = session.get("menu_state_data") or {}
    schedule = session["schedule"]

    if text == "0" or text.lower() in ("back", "cancel", "exit"):
        memory.set_menu_state(phone, None)
        return MAIN_MENU

    # ── Main ──────────────────────────────────────────────────────────────────
    if state == "main":
        if text == "1":
            memory.set_menu_state(phone, None)
            name = _extract_name(ws.read_file(phone, "IDENTITY.md"))
            return f"Chat mode. What's on your mind, {name}?"
        if text == "2":
            memory.set_menu_state(phone, "goals:main")
            return GOALS_MENU
        if text == "3":
            memory.set_menu_state(phone, None)
            return _format_profile(phone)
        if text == "4":
            memory.set_menu_state(phone, "schedule:main")
            return SCHEDULE_MENU
        if text == "5":
            memory.set_menu_state(phone, "settings:main")
            return SETTINGS_MENU
        memory.set_menu_state(phone, None)
        return _handle_chat(phone, text)

    # ── Goals ─────────────────────────────────────────────────────────────────
    if state == "goals:main":
        if text == "1":
            memory.set_menu_state(phone, None)
            return _format_goals(phone)
        if text == "2":
            memory.set_menu_state(phone, "goals:add_text")
            return "📜 *Add a Goal*\n\nType your goal:"
        if text == "3":
            goals = ws.list_goals(phone)
            if not goals:
                memory.set_menu_state(phone, None)
                return "You have no goals yet. Add one via menu → Goals."
            memory.set_menu_state(phone, "goals:remove")
            lines = "\n".join(f"*{i+1}* {g}" for i, (g, _) in enumerate(goals))
            return f"📜 *Remove a Goal*\n\n{lines}\n\nType the number to remove:"
        if text == "4":
            memory.set_menu_state(phone, "goals:add_dream")
            return "📜 *Add a Dream*\n\nWhat life aspiration do you hold?"
        return GOALS_MENU

    if state == "goals:add_text":
        memory.set_menu_state(phone, "goals:add_type", {"goal_text": text.strip()})
        return f"Goal: _{text.strip()}_\n\n" + GOAL_TYPE_PROMPT

    if state == "goals:add_type":
        category_map = {
            "1": "Short-Term Goals",
            "2": "Long-Term Goals",
            "3": "Dreams",
        }
        if text not in category_map:
            return GOAL_TYPE_PROMPT
        ws.add_goal(phone, data.get("goal_text", ""), category_map[text])
        memory.set_menu_state(phone, None)
        return f"✓ Added to your {category_map[text].lower()}.\n\n_{data.get('goal_text', '')}_"

    if state == "goals:add_dream":
        ws.add_goal(phone, text.strip(), "Dreams")
        memory.set_menu_state(phone, None)
        return f"✓ Dream noted.\n\n_{text.strip()}_"

    if state == "goals:remove":
        goals = ws.list_goals(phone)
        try:
            idx = int(text.strip()) - 1
            if 0 <= idx < len(goals):
                goal_text, _ = goals[idx]
                ws.remove_goal(phone, goal_text)
                memory.set_menu_state(phone, None)
                return f"✓ Removed: _{goal_text}_"
            return "Invalid number. Type *0* to cancel."
        except ValueError:
            return "Type a number. Type *0* to cancel."

    # ── Schedule ──────────────────────────────────────────────────────────────
    if state == "schedule:main":
        if text == "1":
            memory.set_menu_state(phone, None)
            return _format_schedule(schedule)
        toggle_map = {
            "2": ("morning_enabled", "Morning message"),
            "3": ("midday_enabled", "Midday check-in"),
            "4": ("evening_enabled", "Evening planning"),
            "5": ("weekly_enabled", "Weekly recap"),
            "6": ("monday_enabled", "Monday update"),
        }
        if text in toggle_map:
            key, label = toggle_map[text]
            schedule[key] = not schedule.get(key, True)
            memory.update_schedule(phone, schedule)
            memory.set_menu_state(phone, None)
            word = "enabled" if schedule[key] else "disabled"
            return f"✓ {label} {word}."
        if text == "7":
            s = schedule
            memory.set_menu_state(phone, "schedule:edit_times")
            return (
                "📜 *Edit Message Times*\n\n"
                f"*1* — Morning  ({s.get('morning_time','07:00')})\n"
                f"*2* — Midday   ({s.get('midday_time','12:00')})\n"
                f"*3* — Evening  ({s.get('evening_time','21:00')})\n"
                f"*4* — Weekly   ({s.get('weekly_day','Sunday').capitalize()} {s.get('weekly_time','19:00')})\n"
                f"*5* — Monday   ({s.get('monday_time','08:00')})\n"
                "*0* — Back"
            )
        return SCHEDULE_MENU

    if state == "schedule:edit_times":
        time_map = {
            "1": ("morning_time", "Morning"),
            "2": ("midday_time", "Midday"),
            "3": ("evening_time", "Evening"),
            "4": ("weekly_time", "Weekly"),
            "5": ("monday_time", "Monday"),
        }
        if text not in time_map:
            return "Type 1-5, or *0* to go back."
        time_key, label = time_map[text]
        memory.set_menu_state(phone, "schedule:set_time", {"time_key": time_key, "label": label})
        return f"📜 Set {label} time\n\nType in HH:MM (24h). Example: 07:30"

    if state == "schedule:set_time":
        if not re.match(r"^\d{2}:\d{2}$", text.strip()):
            return "Invalid format. Use HH:MM (e.g. 07:30):"
        time_key = data.get("time_key", "morning_time")
        label = data.get("label", "")
        schedule[time_key] = text.strip()
        memory.update_schedule(phone, schedule)
        memory.set_menu_state(phone, None)
        try:
            sched.reschedule_user(phone, schedule)
        except Exception:
            logger.warning("Reschedule failed for %s", phone)
        return f"✓ {label} time set to *{text.strip()}*."

    # ── Settings ──────────────────────────────────────────────────────────────
    if state == "settings:main":
        if text == "1":
            memory.set_menu_state(phone, "settings:name")
            return "📜 *Update Name*\n\nWhat should I call you?"
        if text == "2":
            memory.set_menu_state(phone, "settings:timezone")
            return "📜 *Update Timezone*\n\nType your city or timezone (e.g. London, America/New_York):"
        if text == "3":
            memory.set_menu_state(phone, "settings:occupation")
            return "📜 *Update Occupation*\n\nWhat do you do?"
        if text == "4":
            memory.set_menu_state(phone, "settings:interests")
            return "📜 *Update Interests*\n\nList your interests, comma-separated:"
        return SETTINGS_MENU

    if state == "settings:name":
        words = text.strip().split()
        if not words:
            return "Please type a name:"
        name = words[0].capitalize()
        _update_identity_field(phone, "## Name", name)
        memory.set_menu_state(phone, None)
        return f"✓ Name updated to *{name}*."

    if state == "settings:timezone":
        tz = marcus_ai.resolve_timezone(text.strip())
        _update_identity_field(phone, "## Timezone", tz)
        user_md = ws.read_file(phone, "USER.md")
        # Update timezone in USER.md schedule section
        ws.write_file(phone, "USER.md", re.sub(r"(## Timezone\n)[^\n#]*", rf"\g<1>{tz}", user_md))
        memory.set_menu_state(phone, None)
        try:
            sched.reschedule_user(phone, session["schedule"])
        except Exception:
            logger.warning("Reschedule failed for %s after timezone change", phone)
        note = " _(Could not resolve location — using UTC. Try a major city name.)_" if tz == "UTC" else ""
        return f"✓ Timezone set to *{tz}*.{note}"

    if state == "settings:occupation":
        _update_identity_field(phone, "## Occupation", text.strip())
        memory.set_menu_state(phone, None)
        return f"✓ Occupation updated: _{text.strip()}_"

    if state == "settings:interests":
        interests = [i.strip() for i in text.split(",") if i.strip()]
        _update_identity_section(phone, "## Interests", interests)
        memory.set_menu_state(phone, None)
        return f"✓ Interests: {', '.join(interests)}"

    memory.set_menu_state(phone, None)
    return MAIN_MENU


# ── Chat handler ───────────────────────────────────────────────────────────────

def _handle_chat(phone: str, text: str) -> str:
    # "deep:" prefix → use Opus model for this message
    deep = text.lower().startswith("deep:")
    if deep:
        text = text[5:].strip()
    reply = agent.run(phone, text, heartbeat=False, deep=deep)
    memory.increment_msg(phone)
    return reply or "I have nothing to add."


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _format_profile(phone: str) -> str:
    content = ws.read_file(phone, "IDENTITY.md")
    if not content or "[To be filled]" in content:
        return "_No profile yet. Complete onboarding first._"
    return ws.to_whatsapp(content)


def _format_goals(phone: str) -> str:
    content = ws.read_file(phone, "IDENTITY.md")
    m = re.search(
        r"(## Short-Term Goals.*?)(?=\n## [^SLD]|\Z)",
        content, re.DOTALL
    )
    d = re.search(r"(## Dreams.*?)(?=\n## |\Z)", content, re.DOTALL)
    lt = re.search(r"(## Long-Term Goals.*?)(?=\n## |\Z)", content, re.DOTALL)
    parts = [ws.to_whatsapp(x.group(1)) for x in (m, lt, d) if x]
    return "\n\n".join(parts) or "_No goals set yet._"


def _format_schedule(schedule: dict) -> str:
    def s(k): return "✓" if schedule.get(k, True) else "✗"
    return (
        f"📜 *Your Schedule*\n\n"
        f"{s('morning_enabled')} Morning  — {schedule.get('morning_time','07:00')}\n"
        f"{s('midday_enabled')} Midday   — {schedule.get('midday_time','12:00')}\n"
        f"{s('evening_enabled')} Evening  — {schedule.get('evening_time','21:00')}\n"
        f"{s('weekly_enabled')} Weekly   — {schedule.get('weekly_day','Sunday').capitalize()} {schedule.get('weekly_time','19:00')}\n"
        f"{s('monday_enabled')} Monday   — {schedule.get('monday_time','08:00')}\n\n"
        "_All times in your local timezone._"
    )


def _extract_name(identity_content: str) -> str:
    m = re.search(r"## Name\s*\n([^\n#]+)", identity_content)
    if m:
        name = m.group(1).strip()
        if name and name != "[To be filled]":
            return name
    return "friend"


def _update_identity_field(phone: str, section_header: str, value: str):
    """Replace the line immediately following a section header in IDENTITY.md."""
    content = ws.read_file(phone, "IDENTITY.md")
    pattern = rf"({re.escape(section_header)}\n)[^\n#]*"
    ws.write_file(phone, "IDENTITY.md", re.sub(pattern, rf"\g<1>{value}", content))


def _update_identity_section(phone: str, section_header: str, items: list[str]):
    """Replace bullet list under a section header in IDENTITY.md."""
    content = ws.read_file(phone, "IDENTITY.md")
    bullets = "\n".join(f"- {i}" for i in items)
    pattern = rf"({re.escape(section_header)}\n)(.*?)(?=\n##|\Z)"
    replacement = rf"\g<1>{bullets}\n"
    ws.write_file(phone, "IDENTITY.md", re.sub(pattern, replacement, content, flags=re.DOTALL))
