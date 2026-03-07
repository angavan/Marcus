"""
scheduler.py — APScheduler background jobs for proactive daily/weekly messages.

Jobs are rebuilt from the SQLite user table on startup and whenever a user
changes their schedule or timezone.
"""
import logging

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import memory
import marcus_ai
import whatsapp

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")

# (msg_type, time_key, enabled_key)
DAILY_JOBS = [
    ("morning", "morning_time", "morning_enabled"),
    ("midday",  "midday_time",  "midday_enabled"),
    ("evening", "evening_time", "evening_enabled"),
    ("monday",  "monday_time",  "monday_enabled"),
]


def _send(phone: str, msg_type: str):
    """Generate and deliver a proactive message. Logs to conversation history."""
    try:
        user = memory.get_user(phone)
        if not user:
            return
        profile = user["profile"]
        message = marcus_ai.generate_proactive(profile, msg_type)
        whatsapp.send_message(phone, message)
        memory.add_message(phone, "assistant", f"[{msg_type.upper()}] {message}")
        logger.info("Sent %s to %s", msg_type, phone)
    except Exception:
        logger.exception("Failed to send %s to %s", msg_type, phone)


def schedule_user(phone: str, profile: dict):
    """Register all enabled scheduled jobs for a single user."""
    schedule = profile.get("schedule", {})
    tz_str = profile.get("timezone", "UTC")
    try:
        tz = pytz.timezone(tz_str)
    except Exception:
        tz = pytz.UTC

    for msg_type, time_key, enabled_key in DAILY_JOBS:
        job_id = f"{phone}_{msg_type}"
        # Remove stale job
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        if not schedule.get(enabled_key, True):
            continue
        time_str = schedule.get(time_key, "07:00")
        try:
            hour, minute = map(int, time_str.split(":"))
        except ValueError:
            continue

        dow = "mon" if msg_type == "monday" else "*"
        scheduler.add_job(
            _send,
            CronTrigger(day_of_week=dow, hour=hour, minute=minute, timezone=tz),
            args=[phone, msg_type],
            id=job_id,
            replace_existing=True,
        )

    # Weekly recap (separate day-of-week setting)
    weekly_id = f"{phone}_weekly"
    if scheduler.get_job(weekly_id):
        scheduler.remove_job(weekly_id)
    if schedule.get("weekly_enabled", True):
        weekly_time = schedule.get("weekly_time", "19:00")
        day_abbr_map = {
            "sunday": "sun", "monday": "mon", "tuesday": "tue",
            "wednesday": "wed", "thursday": "thu", "friday": "fri", "saturday": "sat",
        }
        day_abbr = day_abbr_map.get(schedule.get("weekly_day", "sunday").lower(), "sun")
        try:
            hour, minute = map(int, weekly_time.split(":"))
            scheduler.add_job(
                _send,
                CronTrigger(day_of_week=day_abbr, hour=hour, minute=minute, timezone=tz),
                args=[phone, "weekly"],
                id=weekly_id,
                replace_existing=True,
            )
        except Exception:
            logger.exception("Failed to schedule weekly job for %s", phone)


def reschedule_user(phone: str, profile: dict):
    """Remove and re-register all jobs for a user (called after settings change)."""
    for job in scheduler.get_jobs():
        if job.id.startswith(f"{phone}_"):
            scheduler.remove_job(job.id)
    schedule_user(phone, profile)


def init_scheduler():
    """Load all users from DB, register their jobs, and start the scheduler."""
    users = memory.get_all_users()
    count = 0
    for user in users:
        if user["profile"].get("name"):  # only schedule fully onboarded users
            schedule_user(user["phone"], user["profile"])
            count += 1
    if not scheduler.running:
        scheduler.start()
    logger.info("Scheduler started — %d jobs registered across %d users", len(scheduler.get_jobs()), count)


def shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)
