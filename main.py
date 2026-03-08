"""
main.py — FastAPI application entry point.

Endpoints
---------
GET  /health   → liveness check
POST /webhook  → Twilio WhatsApp webhook (incoming messages)
"""
import logging
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response

load_dotenv()

import memory
import menu
import scheduler as sched

_REQUIRED_ENV = ["ANTHROPIC_API_KEY", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = [k for k in _REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        logger.critical("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)
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
    """Receive an inbound WhatsApp message from Twilio and reply with TwiML."""
    from whatsapp import parse_webhook
    form = await request.form()
    phone, body = parse_webhook(dict(form))

    if not phone or not body:
        return Response(content=_twiml(""), media_type="application/xml")

    logger.info("Inbound [%s]: %s", phone, body[:80])

    try:
        reply = menu.handle_message(phone, body)
    except Exception:
        logger.exception("Unhandled error for %s", phone)
        reply = "Something went wrong on my end. Type *menu* to reset."

    return Response(content=_twiml(reply), media_type="application/xml")


def _twiml(message: str) -> str:
    safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{safe}</Message></Response>"
