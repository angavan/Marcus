# Marcus
> *What if Marcus Aurelius was my personal life coach and executive assistant?*

A WhatsApp-native AI assistant powered by Claude. Direct, Stoic, proactive — built to help you achieve your goals faster.

---

## What it does

- **Chat freely** — Marcus knows your goals, context, and history. Talk to him like a trusted advisor.
- **Daily check-ins** — Morning inspiration, midday nudge, evening planning. Fully configurable.
- **Weekly recap + Monday update** — Reflect on the week and start the next one with intention.
- **Goal tracking** — Set short-term goals, long-term goals, and life dreams. Marcus holds you to them.
- **Growing memory** — Every ~8 messages, Marcus extracts key learnings about you and updates his context. He gets sharper over time.
- **Full WhatsApp menu** — Navigate with numbers. No app required.

---

## Architecture

```
WhatsApp user
     │
     ▼
Twilio (webhook)
     │
     ▼
FastAPI (main.py)
     ├── menu.py        — menu state machine + routing
     ├── marcus_ai.py   — Claude API (Haiku for chat, Sonnet for tasks)
     ├── memory.py      — SQLite (profiles, history, state)
     └── scheduler.py   — APScheduler (proactive daily messages)
```

**Cost estimate at ~100 messages/day:** < $5/month total.

---

## Setup

### 1. Clone & install

```bash
git clone <repo>
cd Marcus
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in your keys
```

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| `TWILIO_ACCOUNT_SID` | [twilio.com/console](https://twilio.com/console) |
| `TWILIO_AUTH_TOKEN` | Twilio Console |
| `TWILIO_WHATSAPP_FROM` | Twilio Sandbox number (default: `whatsapp:+14155238886`) |

### 3. Run locally

```bash
uvicorn main:app --reload --port 8000
```

### 4. Expose to internet (for Twilio webhook)

```bash
ngrok http 8000
```

Copy the `https://....ngrok.io` URL.

### 5. Configure Twilio WhatsApp Sandbox

1. Go to Twilio Console → Messaging → Try it out → Send a WhatsApp message
2. Join the sandbox by sending the join phrase from your WhatsApp
3. Set the **"When a message comes in"** webhook to: `https://YOUR-NGROK-URL/webhook`
4. Method: `HTTP POST`

### 6. First message

Send any message to the Twilio sandbox number. Marcus will introduce himself and guide you through onboarding: name → timezone → first goal.

---

## WhatsApp commands

| Input | Action |
|---|---|
| Any text | Chat with Marcus |
| `menu` | Main menu |
| `help` | Help text |
| `0` | Back / exit menu |

**Main menu:**
1. Chat freely
2. Goals & Dreams (view, add, remove)
3. Profile (view)
4. Scheduled Messages (toggle, change times)
5. Settings (name, timezone, occupation, interests)

---

## Deploying to production

**Render (recommended — free tier):**

1. Push to GitHub
2. Create a new Web Service on render.com
3. Set all env vars in Render dashboard
4. Update Twilio webhook URL to your Render URL

> **Note on SQLite persistence:** Render free tier resets disk on redeploy. For durable persistence, either use a paid Render plan with a persistent disk, or replace `memory.py` with a PostgreSQL backend (Render provides a free PG instance).

---

## Philosophy

Marcus speaks with the directness of a Roman general and the depth of a Stoic philosopher. He is warm when warmth is needed — firm when firmness serves you better. He will not flatter you. He will help you become who you intend to be.

> *"You have power over your mind, not outside events. Realize this, and you will find strength."*
