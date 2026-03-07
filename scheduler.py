"""
scheduler.py — APScheduler jobs for proactive messages and 30-minute heartbeat.

Scheduled message types:
  morning / midday / evening / weekly / monday — send via generate_proactive()
  heartbeat — run full agentic loop every 30 min; suppress if HEARTBEAT_OK returned

All times respect the user's local timezone (read from workspace IDENTITY.md / USER.md).
Heartbeats only fire during active hours (07:00–22:00 local time).
"""
import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import marcus_ai
import memory
import whatsapp
import workspace as ws

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")

DAILY_JOBS = [
    ("morning", "morning_time", "morning_enabled"),
    ("midday",  "midday_time",  "midday_enabled"),
    ("evening", "evening_time", "evening_enabled"),
    ("monday",  "monday_time",  "monday_enabled"),
]


# ── Job functions ──────────────────────────────────────────────────────────────

def _send_scheduled(phone: str, msg_type: str):
    """Generate and deliver a scheduled proactive message."""
    try:
        message = marcus_ai.generate_proactive(phone, msg_type)
        whatsapp.send_message(phone, message)
        ws.append_transcript(phone, "assistant", f"[{msg_type.upper()}] {message}")
        ws.append_daily_log(phone, f"**Scheduled ({msg_type}):** {message}")
        logger.info("Sent %s to %s", msg_type, phone)
    except Exception:
        logger.exception("Failed to send %s to %s", msg_type, phone)


def _heartbeat(phone: str):
    """
    Run a heartbeat check for a user.
    Uses HEARTBEAT.md as context (lightweight). Suppresses silently if HEARTBEAT_OK.
    Only fires during active hours (07:00–22:00 local time).
    """
    try:
        tz_str = ws.get_timezone(phone)
        try:
            now_local = datetime.now(pytz.timezone(tz_str))
        except Exception:
            now_local = datetime.utcnow()

        if not (7 <= now_local.hour < 22):
            return  # outside active hours — suppress

        from agent import run, HEARTBEAT_OK
        reply = run(phone, "Run your heartbeat checklist now.", heartbeat=True)
        if reply:  # None means HEARTBEAT_OK — silently suppressed
            whatsapp.send_message(phone, reply)
            ws.append_transcript(phone, "assistant", f"[HEARTBEAT] {reply}")
            logger.info("Heartbeat triggered message for %s", phone)
    except Exception:
        logger.exception("Heartbeat failed for %s", phone)


# ── Scheduling ─────────────────────────────────────────────────────────────────

def schedule_user(phone: str, schedule: dict):
    """Register all enabled scheduled jobs for a user."""
    tz_str = ws.get_timezone(phone)
    try:
        tz = pytz.timezone(tz_str)
    except Exception:
        tz = pytz.UTC

    for msg_type, time_key, enabled_key in DAILY_JOBS:
        job_id = f"{phone}_{msg_type}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        if not schedule.get(enabled_key, True):
            continue
        try:
            hour, minute = map(int, schedule.get(time_key, "07:00").split(":"))
        except ValueError:
            continue
        dow = "mon" if msg_type == "monday" else "*"
        scheduler.add_job(
            _send_scheduled,
            CronTrigger(day_of_week=dow, hour=hour, minute=minute, timezone=tz),
            args=[phone, msg_type],
            id=job_id,
            replace_existing=True,
        )

    # Weekly recap
    weekly_id = f"{phone}_weekly"
    if scheduler.get_job(weekly_id):
        scheduler.remove_job(weekly_id)
    if schedule.get("weekly_enabled", True):
        day_abbr = {
            "sunday": "sun", "monday": "mon", "tuesday": "tue",
            "wednesday": "wed", "thursday": "thu", "friday": "fri", "saturday": "sat",
        }.get(schedule.get("weekly_day", "sunday").lower(), "sun")
        try:
            hour, minute = map(int, schedule.get("weekly_time", "19:00").split(":"))
            scheduler.add_job(
                _send_scheduled,
                CronTrigger(day_of_week=day_abbr, hour=hour, minute=minute, timezone=tz),
                args=[phone, "weekly"],
                id=weekly_id,
                replace_existing=True,
            )
        except Exception:
            logger.exception("Failed to schedule weekly for %s", phone)

    # 30-minute heartbeat
    hb_id = f"{phone}_heartbeat"
    if scheduler.get_job(hb_id):
        scheduler.remove_job(hb_id)
    scheduler.add_job(
        _heartbeat,
        IntervalTrigger(minutes=30),
        args=[phone],
        id=hb_id,
        replace_existing=True,
    )


def reschedule_user(phone: str, schedule: dict):
    """Remove and re-register all jobs for a user (called after settings change)."""
    for job in scheduler.get_jobs():
        if job.id.startswith(f"{phone}_"):
            scheduler.remove_job(job.id)
    schedule_user(phone, schedule)


def init_scheduler():
    """Load all onboarded users from DB, register their jobs, start the scheduler."""
    sessions = memory.get_all_sessions()
    count = 0
    for session in sessions:
        phone = session["phone"]
        if not ws.is_new_user(phone):  # only schedule fully onboarded users
            schedule_user(phone, session["schedule"])
            count += 1
    if not scheduler.running:
        scheduler.start()
    logger.info(
        "Scheduler started — %d jobs across %d users",
        len(scheduler.get_jobs()), count,
    )


def shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)
