"""
main.py — FastAPI application entry point.

Endpoints
---------
GET  /health   → liveness check
POST /webhook  → Twilio WhatsApp webhook (incoming messages)
"""
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response

load_dotenv()

import memory
import menu
import scheduler as sched

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    memory.init_db()
    sched.init_scheduler()
    logger.info("Marcus is awake.")
    yield
    sched.shutdown()
    logger.info("Marcus rests.")


app = FastAPI(title="Marcus", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "message": "The obstacle is the way."}


@app.post("/webhook")
async def webhook(request: Request):
    """
    Receive an inbound WhatsApp message from Twilio and reply with TwiML.
    Twilio sends a form-encoded POST with 'From' and 'Body' fields.
    """
    form = await request.form()
    form_data = dict(form)

    phone = form_data.get("From", "").replace("whatsapp:", "").strip()
    body = form_data.get("Body", "").strip()

    if not phone or not body:
        return Response(content=_twiml(""), media_type="application/xml")

    logger.info("Inbound [%s]: %s", phone, body[:80])

    try:
        reply = menu.handle_message(phone, body)
    except Exception:
        logger.exception("Unhandled error for %s", phone)
        reply = "Something went wrong on my end. Type *menu* to reset."

    # After onboarding completes, register scheduler jobs if not yet done
    _maybe_schedule(phone)

    return Response(content=_twiml(reply), media_type="application/xml")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _twiml(message: str) -> str:
    safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{safe}</Message></Response>"


def _maybe_schedule(phone: str):
    """Register scheduler jobs for a user the first time they complete onboarding."""
    user = memory.get_user(phone)
    if not user or not user["profile"].get("name") or user.get("menu_state"):
        return
    existing = [j for j in sched.scheduler.get_jobs() if j.id.startswith(f"{phone}_")]
    if not existing:
        sched.schedule_user(phone, user["profile"])
        logger.info("Scheduled jobs registered for %s", phone)
