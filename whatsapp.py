"""
whatsapp.py — Twilio WhatsApp helpers: send messages, parse incoming webhooks.
"""
import os
from typing import Optional

from twilio.rest import Client

TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(TWILIO_SID, TWILIO_AUTH)
    return _client


def send_message(to_phone: str, body: str):
    """
    Send a WhatsApp message via the Twilio REST API.
    to_phone: E.164 format (e.g. +1234567890) or already prefixed with 'whatsapp:'.
    """
    if not to_phone.startswith("whatsapp:"):
        to_phone = f"whatsapp:{to_phone}"
    get_client().messages.create(from_=TWILIO_FROM, to=to_phone, body=body)


def parse_webhook(form_data: dict) -> tuple[str, str]:
    """
    Extract sender phone and message body from a Twilio webhook POST payload.
    Returns (phone_e164, message_body).
    """
    phone = form_data.get("From", "").replace("whatsapp:", "").strip()
    body = form_data.get("Body", "").strip()
    return phone, body
