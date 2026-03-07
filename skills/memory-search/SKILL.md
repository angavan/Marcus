---
name: memory-search
description: Search MEMORY.md and daily logs for relevant context from past sessions
version: 1.0
---

# Memory Search

Use the `read_memory` tool when:
- The user references something discussed in the past
- You want to check what you already know before responding
- You want to verify a goal or context detail before updating IDENTITY.md

The tool accepts a `query` string of keywords and returns matching lines from MEMORY.md and today's daily log.

## When to Use
- "Didn't we talk about X?" → read_memory before answering
- Before giving advice on a recurring topic, check memory for prior context
- When crafting proactive messages, check memory for recent conversations

## When NOT to Use
- For current conversation context (already in your messages history)
- For simple factual questions not related to the user's history
