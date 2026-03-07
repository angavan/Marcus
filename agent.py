"""
agent.py — ReAct agentic loop for Marcus.

Flow: context assembly → LLM inference → tool execution → re-infer → … → final reply

Tools available to Marcus:
  read_memory     — search MEMORY.md and today's daily log
  write_memory    — persist notes (daily log or permanent MEMORY.md)
  update_identity — rewrite IDENTITY.md with corrected/updated user profile

Heartbeat mode: lightweight context (HEARTBEAT.md only), cheaper model,
suppressed if Marcus responds with exactly HEARTBEAT_OK.
"""
import logging
from typing import Optional

import marcus_ai
import workspace as ws

logger = logging.getLogger(__name__)

HEARTBEAT_OK = "HEARTBEAT_OK"
MAX_ITERATIONS = 5  # circuit breaker

TOOLS = [
    {
        "name": "read_memory",
        "description": (
            "Search MEMORY.md and today's daily log for context relevant to the query. "
            "Use this when the user references something from the past or when you want "
            "to check what you already know before responding."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords or topic to search for."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "write_memory",
        "description": (
            "Write a note to memory. "
            "Set permanent=true to append to MEMORY.md (durable, survives sessions). "
            "Set permanent=false (default) to write to today's daily log (short-term). "
            "Write after every meaningful exchange. Write permanently when you learn "
            "something worth keeping: goal changes, key decisions, important context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The note to write."},
                "permanent": {
                    "type": "boolean",
                    "description": "True = MEMORY.md (long-term). False = daily log (short-term).",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "update_identity",
        "description": (
            "Rewrite IDENTITY.md with updated or corrected user profile information. "
            "Use when the user's goals, context, occupation, or preferences change materially. "
            "Preserve all existing accurate information — only update what changed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Full new Markdown content for IDENTITY.md.",
                }
            },
            "required": ["content"],
        },
    },
]


def _execute(phone: str, tool_name: str, tool_input: dict) -> str:
    if tool_name == "read_memory":
        memory_md = ws.read_file(phone, "MEMORY.md")
        daily = ws.read_daily_log(phone)
        combined = f"MEMORY.md:\n{memory_md}\n\nToday's log:\n{daily}"
        query = tool_input.get("query", "").lower()
        relevant = [
            line for line in combined.splitlines()
            if any(word in line.lower() for word in query.split() if len(word) > 2)
        ]
        return "\n".join(relevant[:60]) or "Nothing found matching that query."

    if tool_name == "write_memory":
        content = tool_input.get("content", "")
        if tool_input.get("permanent", False):
            ws.append_memory(phone, content)
            return "Written to MEMORY.md."
        ws.append_daily_log(phone, content)
        return "Written to today's daily log."

    if tool_name == "update_identity":
        ws.write_file(phone, "IDENTITY.md", tool_input.get("content", ""))
        return "IDENTITY.md updated."

    return f"Unknown tool: {tool_name}"


def run(phone: str, user_message: str, heartbeat: bool = False) -> Optional[str]:
    """
    Run the ReAct loop for a user message.
    Returns the final text reply, or None when a heartbeat has nothing to report.
    """
    system = ws.assemble_context(phone, heartbeat=heartbeat)
    if not system:
        system = "You are Marcus Aurelius, a Stoic life coach and executive assistant."

    summaries = ws.skill_summaries()
    if summaries:
        system += f"\n\n---\n\n<!-- Available Skills -->\n{summaries}"

    history = ws.load_history(phone, limit=20)
    messages = list(history) + [{"role": "user", "content": user_message}]
    model = marcus_ai.TASK if heartbeat else marcus_ai.CHAT

    for iteration in range(MAX_ITERATIONS):
        response = marcus_ai.client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            text = next(
                (block.text.strip() for block in response.content if hasattr(block, "text")),
                "",
            )
            if heartbeat and text == HEARTBEAT_OK:
                return None  # nothing to report — suppress silently

            if not heartbeat:
                ws.append_transcript(phone, "user", user_message)
                ws.append_transcript(phone, "assistant", text)

            return text

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _execute(phone, block.name, block.input)
                    logger.info("[%s] tool %s → %s", phone, block.name, result[:80])
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": result}
                    )
            messages = messages + [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": tool_results},
            ]
            continue

        logger.warning("Unexpected stop_reason=%s at iteration %d", response.stop_reason, iteration)
        break

    logger.warning("ReAct loop exhausted for %s after %d iterations", phone, MAX_ITERATIONS)
    return "I got turned around. Please try again."
