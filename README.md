# Marcus
> *What if Marcus Aurelius was my personal life coach and executive assistant?*

A WhatsApp-native AI assistant powered by Claude. Direct, Stoic, proactive — built to help you achieve your goals faster.

---

## What it does

- **Chat freely** — Marcus knows your goals, context, and history. Talk to him like a trusted advisor.
- **Daily check-ins** — Morning inspiration, midday nudge, evening planning. Fully configurable.
- **Weekly recap + Monday update** — Reflect on the week and start the next one with intention.
- **Goal tracking** — Set short-term goals, long-term goals, and life dreams. Marcus holds you to them.
- **Growing memory** — Marcus writes his own memory after every meaningful exchange. He gets sharper over time.
- **Heartbeat** — Every 30 minutes, Marcus checks if anything needs your attention and reaches out proactively.
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
     ├── agent.py       — ReAct agentic loop (tool-use: read/write memory, update identity)
     ├── marcus_ai.py   — Claude API (Haiku for chat, Sonnet for tasks, Opus for deep)
     ├── workspace.py   — Markdown workspace kernel (identity, memory, transcripts)
     ├── memory.py      — SQLite (session state: menu nav, schedule, msg count)
     └── scheduler.py   — APScheduler (proactive messages + 30-min heartbeat)
```

### Workspace layout (per user)

```
workspace/<phone>/
  AGENTS.md       — Marcus's operating contract (loaded every session)
  SOUL.md         — Marcus's Stoic character and voice
  IDENTITY.md     — user profile: name, timezone, goals, values, interests
  USER.md         — preferences and schedule notes
  MEMORY.md       — long-term memory (Marcus appends as he learns)
  HEARTBEAT.md    — periodic check checklist
  memory/
    YYYY-MM-DD.md — daily working memory logs

transcripts/<phone>.jsonl — immutable JSONL conversation audit trail
```

All workspace files are plain Markdown — inspectable, editable, and version-controllable.

### Models

| Role | Model | When |
|---|---|---|
| CHAT | `claude-haiku-4-5` | Reactive WhatsApp chat (fast, cheap) |
| TASK | `claude-sonnet-4-6` | Proactive messages, onboarding, heartbeat |
| DEEP | `claude-opus-4-6` | User-requested only (prefix message with `deep:`) |

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

Send any message to the Twilio sandbox number. Marcus will introduce himself and guide you through onboarding: name + location → 5 intake questions → identity confirmation.

---

## WhatsApp commands

| Input | Action |
|---|---|
| Any text | Chat with Marcus |
| `menu` | Main menu |
| `help` | Help text |
| `deep: <message>` | Use Opus model for this message |
| `0` | Back / exit menu |

**Main menu:**
1. Chat freely
2. Goals & Dreams (view, add, remove)
3. Profile (view)
4. Scheduled Messages (toggle, change times)
5. Settings (name, timezone, occupation, interests)

---

## Skills

Skills extend Marcus's capabilities. Each skill lives in `skills/<name>/SKILL.md` with YAML frontmatter describing its purpose. Summaries are injected into every session; full content loads on demand.

Built-in skills: `memory-search`, `memory-write`.

To add a skill, create `skills/<name>/SKILL.md` following the existing pattern.

---

## Deploying to production

**Render (recommended — free tier):**

1. Push to GitHub
2. Create a new Web Service on render.com
3. Set all env vars in Render dashboard
4. Update Twilio webhook URL to your Render URL

> **Note on persistence:** Render free tier resets disk on redeploy. For durable persistence, either use a paid Render plan with a persistent disk, or back the `workspace/` and `transcripts/` directories with object storage (S3, R2). SQLite (`marcus.db`) only stores session state — workspace files are what matter.

---

## Philosophy

Marcus speaks with the directness of a Roman general and the depth of a Stoic philosopher. He is warm when warmth is needed — firm when firmness serves you better. He will not flatter you. He will help you become who you intend to be.

> *"You have power over your mind, not outside events. Realize this, and you will find strength."*
