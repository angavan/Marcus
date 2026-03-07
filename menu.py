"""
menu.py — WhatsApp message routing and menu state machine.

States
------
None                → free chat mode (default)
"main"              → main menu shown, awaiting selection
"setup:name"        → onboarding: waiting for name
"setup:timezone"    → onboarding: waiting for timezone
"setup:goals"       → onboarding: waiting for first goal
"goals:main"        → goals submenu
"goals:add_text"    → waiting for new goal text
"goals:add_type"    → waiting for goal category selection
"goals:add_dream"   → waiting for dream text
"goals:remove"      → waiting for goal number to remove
"schedule:main"     → schedule submenu
"schedule:edit_times" → waiting for time slot selection
"schedule:set_time" → waiting for HH:MM input
"settings:main"     → settings submenu
"settings:name"     → waiting for new name
"settings:timezone" → waiting for new timezone
"settings:occupation" → waiting for occupation
"settings:interests" → waiting for interests list
"""
import re
from typing import Optional

import memory
import marcus_ai

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

TIMEZONE_PROMPT = """\
Type your timezone in standard format. Examples:
• America/New_York
• Europe/London
• Asia/Tokyo
• America/Los_Angeles
• UTC

*Type your timezone:*\
"""

ONBOARDING_WELCOME = """\
📜 *I am Marcus.*
Not a ghost — but a spirit forged from two millennia of hard-won wisdom, \
put to work in your service.

I will serve as your life coach, strategist, and executive assistant. \
I will remember what matters to you, check in daily, and hold you \
accountable to your highest ambitions.

To serve you well, I must first know you.

*What is your name?*\
"""

HELP_TEXT = """\
📜 *MARCUS — Help*

Type *menu* anytime — main menu.
Type *help* — this message.

What I do:
• Chat with you, remember context across conversations
• Track your goals and dreams
• Send daily check-ins (morning, midday, evening)
• Send weekly recaps and Monday updates
• Proactively offer insights without being asked

I am not a chatbot. I am your ally.\
"""


# ── Entry point ────────────────────────────────────────────────────────────────

def handle_message(phone: str, text: str) -> str:
    """Route an incoming WhatsApp message and return a reply string."""
    text = text.strip()
    lower = text.lower()

    # Get or create user
    user = memory.get_user(phone)
    if not user:
        user = memory.create_user(phone)
        memory.set_menu_state(phone, "setup:name")
        return ONBOARDING_WELCOME

    menu_state = user.get("menu_state")

    # ── Global shortcuts (always work) ──────────────────────────────────────
    if lower in ("menu", "home", "start"):
        memory.set_menu_state(phone, "main")
        return MAIN_MENU

    if lower in ("help", "?"):
        return HELP_TEXT

    # ── Onboarding ──────────────────────────────────────────────────────────
    if menu_state and menu_state.startswith("setup:"):
        return _handle_setup(phone, user, text)

    # ── Menu navigation ─────────────────────────────────────────────────────
    if menu_state:
        return _handle_menu_nav(phone, user, text)

    # ── Free chat ───────────────────────────────────────────────────────────
    return _handle_chat(phone, user, text)


# ── Onboarding flow ────────────────────────────────────────────────────────────

def _handle_setup(phone: str, user: dict, text: str) -> str:
    state = user["menu_state"]
    profile = user["profile"]

    if state == "setup:name":
        name = text.strip().split()[0].capitalize()
        profile["name"] = name
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, "setup:timezone")
        return f"Good. *{name}*.\n\n" + TIMEZONE_PROMPT

    if state == "setup:timezone":
        import pytz
        tz_input = text.strip()
        if tz_input not in pytz.all_timezones:
            return (
                f"I don't recognize *{tz_input}*. Use a standard format:\n"
                "• America/New_York\n• Europe/London\n• Asia/Tokyo\n\n"
                "*Try again:*"
            )
        profile["timezone"] = tz_input
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, "setup:goals")
        return (
            f"Noted — *{tz_input}*.\n\n"
            f"Now, *{profile['name']}* — what is your single most important goal "
            "right now? Speak plainly. You can add more later."
        )

    if state == "setup:goals":
        profile["goals"]["short_term"].append(text.strip())
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, None)
        name = profile["name"]
        return (
            f"Noted. I will hold you to this.\n\n"
            f"📜 *Setup complete, {name}.*\n\n"
            "• Just type to talk to me\n"
            "• Type *menu* to navigate\n"
            "• Add more goals via menu → Goals\n\n"
            f"I will reach out each morning, midday, and evening. "
            f"The work begins now, {name}."
        )

    return "Something went wrong. Type *menu* to reset."


# ── Menu navigation ────────────────────────────────────────────────────────────

def _handle_menu_nav(phone: str, user: dict, text: str) -> str:
    state = user["menu_state"]
    profile = user["profile"]
    data = user.get("menu_state_data") or {}
    lower = text.lower()

    # Back / cancel
    if text == "0" or lower in ("back", "cancel", "exit"):
        memory.set_menu_state(phone, None)
        return MAIN_MENU

    # ── Main menu ────────────────────────────────────────────────────────────
    if state == "main":
        if text == "1":
            memory.set_menu_state(phone, None)
            name = profile.get("name", "friend")
            return f"Chat mode. What's on your mind, {name}?"
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

    # ── Goals ────────────────────────────────────────────────────────────────
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
                return "You have no goals yet. Add one via menu → Goals → Add a goal."
            memory.set_menu_state(phone, "goals:remove")
            return f"📜 *Remove a Goal*\n\n{_goals_numbered_text(profile)}\n\nType the number to remove:"
        if text == "4":
            memory.set_menu_state(phone, "goals:add_dream")
            return "📜 *Add a Dream*\n\nWhat life aspiration do you hold? Type it:"
        return GOALS_MENU

    if state == "goals:add_text":
        memory.set_menu_state(phone, "goals:add_type", {"goal_text": text.strip()})
        return f"Goal: _{text.strip()}_\n\n" + GOAL_TYPE_PROMPT

    if state == "goals:add_type":
        goal_text = data.get("goal_text", "")
        goals = profile.setdefault("goals", {"short_term": [], "long_term": [], "dreams": []})
        category_map = {"1": ("short_term", "short-term goals"), "2": ("long_term", "long-term goals"), "3": ("dreams", "dreams")}
        if text not in category_map:
            return GOAL_TYPE_PROMPT
        cat_key, cat_label = category_map[text]
        goals[cat_key].append(goal_text)
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

    # ── Schedule ─────────────────────────────────────────────────────────────
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
            profile["schedule"] = schedule
            memory.update_profile(phone, profile)
            memory.set_menu_state(phone, None)
            word = "enabled" if schedule[key] else "disabled"
            return f"✓ {label} {word}."
        if text == "7":
            s = schedule
            memory.set_menu_state(phone, "schedule:edit_times")
            return (
                "📜 *Edit Message Times*\n\n"
                f"*1* — Morning (currently {s.get('morning_time','07:00')})\n"
                f"*2* — Midday (currently {s.get('midday_time','12:00')})\n"
                f"*3* — Evening (currently {s.get('evening_time','21:00')})\n"
                f"*4* — Weekly (currently {s.get('weekly_time','19:00')} on {s.get('weekly_day','sunday').capitalize()})\n"
                f"*5* — Monday (currently {s.get('monday_time','08:00')})\n"
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
        schedule = profile.setdefault("schedule", {})
        schedule[time_key] = text.strip()
        profile["schedule"] = schedule
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, None)
        # Kick scheduler to re-register jobs
        try:
            import scheduler as sched
            sched.reschedule_user(phone, profile)
        except Exception:
            pass
        return f"✓ {label} time set to *{text.strip()}*."

    # ── Settings ─────────────────────────────────────────────────────────────
    if state == "settings:main":
        if text == "1":
            memory.set_menu_state(phone, "settings:name")
            return "📜 *Update Name*\n\nWhat should I call you?"
        if text == "2":
            memory.set_menu_state(phone, "settings:timezone")
            return "📜 *Update Timezone*\n\n" + TIMEZONE_PROMPT
        if text == "3":
            memory.set_menu_state(phone, "settings:occupation")
            return "📜 *Update Occupation*\n\nWhat do you do? (role, industry, or brief description)"
        if text == "4":
            memory.set_menu_state(phone, "settings:interests")
            return "📜 *Update Interests*\n\nList your main interests, comma-separated:"
        return SETTINGS_MENU

    if state == "settings:name":
        name = text.strip().split()[0].capitalize()
        profile["name"] = name
        memory.update_profile(phone, profile)
        memory.set_menu_state(phone, None)
        return f"✓ Name updated to *{name}*."

    if state == "settings:timezone":
        import pytz
        if text.strip() in pytz.all_timezones:
            profile["timezone"] = text.strip()
            memory.update_profile(phone, profile)
            memory.set_menu_state(phone, None)
            try:
                import scheduler as sched
                sched.reschedule_user(phone, profile)
            except Exception:
                pass
            return f"✓ Timezone set to *{text.strip()}*."
        return f"Unknown timezone: *{text.strip()}*. Try again (e.g. America/New_York):"

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

    # Fallback
    memory.set_menu_state(phone, None)
    return MAIN_MENU


# ── Chat handler ───────────────────────────────────────────────────────────────

def _handle_chat(phone: str, user: dict, text: str) -> str:
    profile = user["profile"]
    history = memory.get_history(phone)

    reply = marcus_ai.chat(profile, history, text)

    memory.add_message(phone, "user", text)
    memory.add_message(phone, "assistant", reply)

    # Every 8 messages extract new learnings and update context notes
    msg_count = user.get("msg_count", 0)
    if msg_count > 0 and msg_count % 8 == 0:
        try:
            recent = memory.get_history(phone, limit=10)
            new_notes = marcus_ai.extract_and_update_notes(profile, recent)
            if new_notes:
                profile["context_notes"] = new_notes
                memory.update_profile(phone, profile)
        except Exception:
            pass  # never fail a chat response due to note extraction

    return reply


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _format_profile(profile: dict) -> str:
    name = profile.get("name") or "Not set"
    occupation = profile.get("occupation") or "Not set"
    tz = profile.get("timezone", "UTC")
    interests = ", ".join(profile.get("preferences", {}).get("interests", [])) or "Not set"
    goals = profile.get("goals", {})
    st = "\n  • ".join(goals.get("short_term", [])) or "None"
    lt = "\n  • ".join(goals.get("long_term", [])) or "None"
    dr = "\n  • ".join(goals.get("dreams", [])) or "None"
    return (
        f"📜 *Your Profile*\n\n"
        f"*Name:* {name}\n"
        f"*Occupation:* {occupation}\n"
        f"*Timezone:* {tz}\n"
        f"*Interests:* {interests}\n\n"
        f"*Short-term goals:*\n  • {st}\n\n"
        f"*Long-term goals:*\n  • {lt}\n\n"
        f"*Dreams:*\n  • {dr}\n\n"
        "_Type *menu* → Settings to update._"
    )


def _format_goals(profile: dict) -> str:
    goals = profile.get("goals", {})
    st = "\n  • ".join(goals.get("short_term", [])) or "None set"
    lt = "\n  • ".join(goals.get("long_term", [])) or "None set"
    dr = "\n  • ".join(goals.get("dreams", [])) or "None set"
    return (
        f"📜 *Your Goals & Dreams*\n\n"
        f"*Short-term:*\n  • {st}\n\n"
        f"*Long-term:*\n  • {lt}\n\n"
        f"*Dreams:*\n  • {dr}"
    )


def _goals_flat(profile: dict) -> list[tuple[str, str]]:
    goals = profile.get("goals", {})
    flat = []
    for g in goals.get("short_term", []):
        flat.append((g, "short_term"))
    for g in goals.get("long_term", []):
        flat.append((g, "long_term"))
    for g in goals.get("dreams", []):
        flat.append((g, "dreams"))
    return flat


def _goals_numbered_text(profile: dict) -> str:
    flat = _goals_flat(profile)
    labels = {"short_term": "ST", "long_term": "LT", "dreams": "✦"}
    return "\n".join(f"*{i+1}* [{labels[cat]}] {text}" for i, (text, cat) in enumerate(flat))


def _format_schedule(schedule: dict) -> str:
    def s(key):
        return "✓" if schedule.get(key, True) else "✗"
    return (
        f"📜 *Your Schedule*\n\n"
        f"{s('morning_enabled')} Morning     — {schedule.get('morning_time','07:00')}\n"
        f"{s('midday_enabled')} Midday      — {schedule.get('midday_time','12:00')}\n"
        f"{s('evening_enabled')} Evening     — {schedule.get('evening_time','21:00')}\n"
        f"{s('weekly_enabled')} Weekly      — {schedule.get('weekly_day','Sunday').capitalize()} {schedule.get('weekly_time','19:00')}\n"
        f"{s('monday_enabled')} Monday      — {schedule.get('monday_time','08:00')}\n\n"
        "_All times in your local timezone._"
    )
