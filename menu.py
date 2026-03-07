"""
menu.py — WhatsApp message routing and menu state machine.

States
------
None                  → free chat (default)
"main"                → main menu shown
"setup:basics"        → onboarding step 1 — name + location
"setup:intake"        → onboarding step 2 — 5 deep questions (bulk)
"setup:confirm"       → onboarding step 3 — show parsed profile, await confirmation
"goals:main"          → goals submenu
"goals:add_text"      → waiting for goal text
"goals:add_type"      → waiting for goal category (1/2/3)
"goals:add_dream"     → waiting for dream text
"goals:remove"        → waiting for goal number to remove
"schedule:main"       → schedule submenu
"schedule:edit_times" → waiting for time slot selection
"schedule:set_time"   → waiting for HH:MM input
"settings:main"       → settings submenu
"settings:name"       → waiting for new name
"settings:timezone"   → waiting for new timezone
"settings:occupation" → waiting for occupation
"settings:interests"  → waiting for interests list
"""
import logging
import re

import pytz

import marcus_ai
import memory
import scheduler as sched

logger = logging.getLogger(__name__)

# ── Menu strings ───────────────────────────────────────────────────────────────

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

What I do:
• Chat and remember context across conversations
• Track your goals, dreams, and values
• Daily check-ins: morning, midday, evening
• Weekly recaps and Monday activations
• Proactively offer insights without being asked

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

*1.* What do you do? (work, business, study — describe it briefly)
*2.* What are your current goals — the ones you think about most?
*3.* What are your deeper dreams or long-term ambitions?
*4.* What are your biggest current challenges or obstacles?
*5.* What do you value most in life? What principles guide you?

Write freely. Take your time. I'll build your profile from what you give me.\
"""

CONFIRM_TEMPLATE = """\
📜 *Here's my first picture of you:*

*{name}* | {occupation}
*Timezone:* {timezone}

*Short-term goals:*
{short_term}

*Long-term goals:*
{long_term}

*Dreams:*
{dreams}

*Values:* {values}
*Interests:* {interests}

*My first read:* {context_notes}

Does this capture you accurately? Say *"looks good"* to continue, or tell me what to correct.\
"""

_CONFIRM_YES = {"yes", "looks good", "good", "correct", "ok", "done", "perfect", "yep", "right",
                "confirmed", "that's right", "all good", "accurate"}


# ── Entry point ────────────────────────────────────────────────────────────────

def handle_message(phone: str, text: str) -> str:
    text = text.strip()
    lower = text.lower()

    user = memory.get_user(phone)
    if not user:
        user = memory.create_user(phone)
        memory.set_menu_state(phone, "setup:basics")
        return ONBOARDING_WELCOME

    menu_state = user.get("menu_state")

    # Global shortcuts
    if lower in ("menu", "home", "start"):
        memory.set_menu_state(phone, "main")
        return MAIN_MENU
    if lower in ("help", "?"):
        return HELP_TEXT

    if menu_state and menu_state.startswith("setup:"):
        return _handle_setup(phone, user, text)
    if menu_state:
        return _handle_menu_nav(phone, user, text)

    return _handle_chat(phone, user, text)


# ── Onboarding ─────────────────────────────────────────────────────────────────

def _handle_setup(phone: str, user: dict, text: str) -> str:
    state = user["menu_state"]
    profile = user["profile"]
    data = user.get("menu_state_data") or {}

    if state == "setup:basics":
        parsed = marcus_ai.parse_basics(text)
        name = parsed.get("name", text.strip().split()[0]).capitalize()
        tz = marcus_ai.resolve_timezone(parsed.get("location", text))
        profile["name"] = name
        profile["timezone"] = tz
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, "setup:intake")
        return INTAKE_QUESTIONS.format(name=name)

    if state == "setup:intake":
        parsed = marcus_ai.parse_intake(text)
        if parsed:
            # Merge parsed data; protect name + timezone already collected in basics
            for key, val in parsed.items():
                if key not in ("name", "timezone"):
                    profile[key] = val
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, "setup:confirm", {"intake_text": text})
        return _format_confirm(profile)

    if state == "setup:confirm":
        if any(w in text.lower() for w in _CONFIRM_YES) or text.lower() in _CONFIRM_YES:
            memory.set_menu_state(phone, None)
            try:
                sched.schedule_user(phone, profile)
            except Exception:
                logger.warning("Failed to schedule jobs for %s after onboarding", phone)
            name = profile.get("name", "friend")
            return (
                f"📜 *Profile saved, {name}.*\n\n"
                "You can update anything via menu → Settings.\n\n"
                "I'll reach out each morning, midday, and evening. "
                f"The work begins now, {name}."
            )
        # Treat message as correction — re-parse original answers + correction
        original_text = data.get("intake_text", "")
        corrected = marcus_ai.parse_intake(
            f"Original answers:\n{original_text}\n\nUser correction: {text}"
        )
        if corrected:
            for key, val in corrected.items():
                if key not in ("name", "timezone"):
                    profile[key] = val
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, "setup:confirm", {"intake_text": original_text})
        return "✓ Updated.\n\n" + _format_confirm(profile)

    return "Something went wrong. Type *menu* to reset."


# ── Menu navigation ────────────────────────────────────────────────────────────

def _handle_menu_nav(phone: str, user: dict, text: str) -> str:
    state = user["menu_state"]
    profile = user["profile"]
    data = user.get("menu_state_data") or {}

    if text == "0" or text.lower() in ("back", "cancel", "exit"):
        memory.set_menu_state(phone, None)
        return MAIN_MENU

    # ── Main ──────────────────────────────────────────────────────────────────
    if state == "main":
        if text == "1":
            memory.set_menu_state(phone, None)
            return f"Chat mode. What's on your mind, {profile.get('name', 'friend')}?"
        if text == "2":
            memory.set_menu_state(phone, "goals:main")
            return GOALS_MENU
        if text == "3":
            memory.set_menu_state(phone, None)
            return _format_profile(profile)
        if text == "4":
            memory.set_menu_state(phone, "schedule:main")
            return SCHEDULE_MENU
        if text == "5":
            memory.set_menu_state(phone, "settings:main")
            return SETTINGS_MENU
        # Unrecognised input while in main menu → treat as chat
        memory.set_menu_state(phone, None)
        return _handle_chat(phone, user, text)

    # ── Goals ─────────────────────────────────────────────────────────────────
    if state == "goals:main":
        if text == "1":
            memory.set_menu_state(phone, None)
            return _format_goals(profile)
        if text == "2":
            memory.set_menu_state(phone, "goals:add_text")
            return "📜 *Add a Goal*\n\nType your goal:"
        if text == "3":
            flat = _goals_flat(profile)
            if not flat:
                memory.set_menu_state(phone, None)
                return "You have no goals yet. Add one via menu → Goals."
            memory.set_menu_state(phone, "goals:remove")
            return f"📜 *Remove a Goal*\n\n{_goals_numbered_text(profile)}\n\nType the number to remove:"
        if text == "4":
            memory.set_menu_state(phone, "goals:add_dream")
            return "📜 *Add a Dream*\n\nWhat life aspiration do you hold?"
        return GOALS_MENU

    if state == "goals:add_text":
        memory.set_menu_state(phone, "goals:add_type", {"goal_text": text.strip()})
        return f"Goal: _{text.strip()}_\n\n" + GOAL_TYPE_PROMPT

    if state == "goals:add_type":
        goal_text = data.get("goal_text", "")
        category_map = {
            "1": ("short_term", "short-term goals"),
            "2": ("long_term", "long-term goals"),
            "3": ("dreams", "dreams"),
        }
        if text not in category_map:
            return GOAL_TYPE_PROMPT
        cat_key, cat_label = category_map[text]
        profile["goals"].setdefault(cat_key, []).append(goal_text)
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, None)
        return f"✓ Added to your {cat_label}.\n\n_{goal_text}_\n\nHold yourself to it."

    if state == "goals:add_dream":
        profile["goals"].setdefault("dreams", []).append(text.strip())
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, None)
        return f"✓ Dream noted.\n\n_{text.strip()}_\n\nKeep it in sight."

    if state == "goals:remove":
        flat = _goals_flat(profile)
        try:
            idx = int(text.strip()) - 1
            if 0 <= idx < len(flat):
                goal_text, cat_key = flat[idx]
                profile["goals"][cat_key].remove(goal_text)
                memory.update_profile(phone, profile)
                memory.set_menu_state(phone, None)
                return f"✓ Removed: _{goal_text}_"
            return "Invalid number. Type *0* to cancel."
        except ValueError:
            return "Type a number. Type *0* to cancel."

    # ── Schedule ──────────────────────────────────────────────────────────────
    if state == "schedule:main":
        schedule = profile.setdefault("schedule", {})
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
            memory.update_profile(phone, profile)
            memory.set_menu_state(phone, None)
            word = "enabled" if schedule[key] else "disabled"
            return f"✓ {label} {word}."
        if text == "7":
            s = schedule
            memory.set_menu_state(phone, "schedule:edit_times")
            return (
                "📜 *Edit Message Times*\n\n"
                f"*1* — Morning  (currently {s.get('morning_time','07:00')})\n"
                f"*2* — Midday   (currently {s.get('midday_time','12:00')})\n"
                f"*3* — Evening  (currently {s.get('evening_time','21:00')})\n"
                f"*4* — Weekly   (currently {s.get('weekly_day','Sunday').capitalize()} {s.get('weekly_time','19:00')})\n"
                f"*5* — Monday   (currently {s.get('monday_time','08:00')})\n"
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
            return "Type a number 1-5, or *0* to go back."
        time_key, label = time_map[text]
        memory.set_menu_state(phone, "schedule:set_time", {"time_key": time_key, "label": label})
        return f"📜 Set {label} time\n\nType in HH:MM format (24h). Example: 07:30"

    if state == "schedule:set_time":
        if not re.match(r"^\d{2}:\d{2}$", text.strip()):
            return "Invalid format. Use HH:MM (e.g. 07:30). Try again:"
        time_key = data.get("time_key", "morning_time")
        label = data.get("label", "")
        profile.setdefault("schedule", {})[time_key] = text.strip()
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, None)
        try:
            sched.reschedule_user(phone, profile)
        except Exception:
            logger.warning("Failed to reschedule %s after time change", phone)
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
            return "📜 *Update Interests*\n\nList your main interests, comma-separated:"
        return SETTINGS_MENU

    if state == "settings:name":
        profile["name"] = text.strip().split()[0].capitalize()
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, None)
        return f"✓ Name updated to *{profile['name']}*."

    if state == "settings:timezone":
        tz = marcus_ai.resolve_timezone(text.strip())
        profile["timezone"] = tz
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, None)
        try:
            sched.reschedule_user(phone, profile)
        except Exception:
            logger.warning("Failed to reschedule %s after timezone change", phone)
        return f"✓ Timezone set to *{tz}*."

    if state == "settings:occupation":
        profile["occupation"] = text.strip()
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, None)
        return f"✓ Occupation updated: _{text.strip()}_"

    if state == "settings:interests":
        interests = [i.strip() for i in text.split(",") if i.strip()]
        profile.setdefault("preferences", {})["interests"] = interests
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, None)
        return f"✓ Interests: {', '.join(interests)}"

    memory.set_menu_state(phone, None)
    return MAIN_MENU


# ── Chat handler ───────────────────────────────────────────────────────────────

def _handle_chat(phone: str, user: dict, text: str) -> str:
    profile = user["profile"]
    history = memory.get_history(phone)   # fetched once; reused for both chat and note extraction

    reply = marcus_ai.chat(profile, history, text)

    memory.add_message(phone, "user", text)
    memory.add_message(phone, "assistant", reply)

    # Every 8 messages, extract learnings and update context notes (Sonnet)
    if user.get("msg_count", 0) % 8 == 0 and user.get("msg_count", 0) > 0:
        try:
            new_notes = marcus_ai.extract_notes(profile, history[-10:])
            if new_notes:
                profile["context_notes"] = new_notes
                memory.update_profile(phone, profile)
        except Exception:
            logger.warning("Note extraction failed for %s", phone)

    return reply


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _fmt_list(items: list) -> str:
    return "\n  • ".join(items) if items else "None"


def _format_profile(profile: dict) -> str:
    g = profile.get("goals", {})
    p = profile.get("preferences", {})
    return (
        f"📜 *Your Profile*\n\n"
        f"*Name:* {profile.get('name') or 'Not set'}\n"
        f"*Occupation:* {profile.get('occupation') or 'Not set'}\n"
        f"*Timezone:* {profile.get('timezone', 'UTC')}\n"
        f"*Interests:* {', '.join(p.get('interests', [])) or 'Not set'}\n"
        f"*Values:* {', '.join(p.get('values', [])) or 'Not set'}\n\n"
        f"*Short-term goals:*\n  • {_fmt_list(g.get('short_term', []))}\n\n"
        f"*Long-term goals:*\n  • {_fmt_list(g.get('long_term', []))}\n\n"
        f"*Dreams:*\n  • {_fmt_list(g.get('dreams', []))}\n\n"
        "_Type *menu* → Settings to update._"
    )


def _format_goals(profile: dict) -> str:
    g = profile.get("goals", {})
    return (
        f"📜 *Your Goals & Dreams*\n\n"
        f"*Short-term:*\n  • {_fmt_list(g.get('short_term', []))}\n\n"
        f"*Long-term:*\n  • {_fmt_list(g.get('long_term', []))}\n\n"
        f"*Dreams:*\n  • {_fmt_list(g.get('dreams', []))}"
    )


def _goals_flat(profile: dict) -> list[tuple[str, str]]:
    g = profile.get("goals", {})
    return (
        [(t, "short_term") for t in g.get("short_term", [])]
        + [(t, "long_term") for t in g.get("long_term", [])]
        + [(t, "dreams") for t in g.get("dreams", [])]
    )


def _goals_numbered_text(profile: dict) -> str:
    labels = {"short_term": "ST", "long_term": "LT", "dreams": "✦"}
    return "\n".join(
        f"*{i+1}* [{labels[cat]}] {text}"
        for i, (text, cat) in enumerate(_goals_flat(profile))
    )


def _format_schedule(schedule: dict) -> str:
    def s(key): return "✓" if schedule.get(key, True) else "✗"
    return (
        f"📜 *Your Schedule*\n\n"
        f"{s('morning_enabled')} Morning  — {schedule.get('morning_time','07:00')}\n"
        f"{s('midday_enabled')} Midday   — {schedule.get('midday_time','12:00')}\n"
        f"{s('evening_enabled')} Evening  — {schedule.get('evening_time','21:00')}\n"
        f"{s('weekly_enabled')} Weekly   — {schedule.get('weekly_day','Sunday').capitalize()} {schedule.get('weekly_time','19:00')}\n"
        f"{s('monday_enabled')} Monday   — {schedule.get('monday_time','08:00')}\n\n"
        "_All times in your local timezone._"
    )


def _format_confirm(profile: dict) -> str:
    g = profile.get("goals", {})
    p = profile.get("preferences", {})
    def fmt(lst): return "\n".join(f"  • {i}" for i in lst) if lst else "  (none)"
    return CONFIRM_TEMPLATE.format(
        name=profile.get("name", ""),
        occupation=profile.get("occupation") or "not specified",
        timezone=profile.get("timezone", "UTC"),
        short_term=fmt(g.get("short_term", [])),
        long_term=fmt(g.get("long_term", [])),
        dreams=fmt(g.get("dreams", [])),
        values=", ".join(p.get("values", [])) or "not specified",
        interests=", ".join(p.get("interests", [])) or "not specified",
        context_notes=profile.get("context_notes") or "(none yet)",
    )
