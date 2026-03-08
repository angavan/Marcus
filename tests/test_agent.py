"""
tests/test_agent.py — Unit tests for agent.py

Tests tool dispatch (_execute) and model selection via run().
The Anthropic client is mocked; no real API calls are made.
"""
from unittest.mock import MagicMock

import pytest

import agent
import marcus_ai
import workspace as ws


PHONE = "+15550001234"


# ── _execute: tool dispatch ────────────────────────────────────────────────────

class TestExecute:
    def test_read_memory_returns_relevant_lines(self):
        ws.write_file(PHONE, "MEMORY.md", "- User loves philosophy\n- User dislikes noise\n")
        result = agent._execute(PHONE, "read_memory", {"query": "philosophy"})
        assert "philosophy" in result.lower()

    def test_read_memory_no_match(self):
        ws.write_file(PHONE, "MEMORY.md", "- User loves philosophy\n")
        result = agent._execute(PHONE, "read_memory", {"query": "quantum physics"})
        assert result == "Nothing found matching that query."

    def test_write_memory_daily(self):
        ws.user_dir(PHONE).mkdir(parents=True, exist_ok=True)
        (ws.user_dir(PHONE) / "memory").mkdir(exist_ok=True)
        result = agent._execute(PHONE, "write_memory", {"content": "Today I exercised.", "permanent": False})
        assert result == "Written to today's daily log."
        log = ws.read_daily_log(PHONE)
        assert "Today I exercised." in log

    def test_write_memory_permanent(self):
        ws.write_file(PHONE, "MEMORY.md", "# MEMORY\n")
        result = agent._execute(PHONE, "write_memory", {"content": "User is a founder.", "permanent": True})
        assert result == "Written to MEMORY.md."
        assert "User is a founder." in ws.read_file(PHONE, "MEMORY.md")

    def test_update_identity(self):
        result = agent._execute(PHONE, "update_identity", {"content": "# IDENTITY\n## Name\nBob"})
        assert result == "IDENTITY.md updated."
        assert "Bob" in ws.read_file(PHONE, "IDENTITY.md")

    def test_unknown_tool(self):
        result = agent._execute(PHONE, "nonexistent_tool", {})
        assert "Unknown tool" in result


# ── run(): model selection ─────────────────────────────────────────────────────

def _make_response(text="OK", stop_reason="end_turn"):
    block = MagicMock()
    block.text = text
    block.type = "text"
    resp = MagicMock()
    resp.stop_reason = stop_reason
    resp.content = [block]
    return resp


def _setup_workspace():
    for f in ["AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md"]:
        ws.write_file(PHONE, f, f"# {f}\n")


class TestRun:
    def test_regular_message_uses_chat_model(self, monkeypatch):
        _setup_workspace()
        used_model = []

        def fake_create(**kwargs):
            used_model.append(kwargs.get("model"))
            return _make_response("Hello!")

        monkeypatch.setattr(marcus_ai.client.messages, "create", fake_create)
        agent.run(PHONE, "Hi", heartbeat=False, deep=False)
        assert used_model[0] == marcus_ai.CHAT

    def test_deep_message_uses_opus_model(self, monkeypatch):
        _setup_workspace()
        used_model = []

        def fake_create(**kwargs):
            used_model.append(kwargs.get("model"))
            return _make_response("Deep reply.")

        monkeypatch.setattr(marcus_ai.client.messages, "create", fake_create)
        agent.run(PHONE, "Analyse my life.", heartbeat=False, deep=True)
        assert used_model[0] == marcus_ai.DEEP

    def test_heartbeat_uses_task_model(self, monkeypatch):
        _setup_workspace()
        ws.write_file(PHONE, "HEARTBEAT.md", "# Heartbeat\n- check goals\n")
        used_model = []

        def fake_create(**kwargs):
            used_model.append(kwargs.get("model"))
            return _make_response(agent.HEARTBEAT_OK)

        monkeypatch.setattr(marcus_ai.client.messages, "create", fake_create)
        result = agent.run(PHONE, "Run heartbeat.", heartbeat=True)
        assert used_model[0] == marcus_ai.TASK
        assert result is None  # HEARTBEAT_OK suppressed silently

    def test_circuit_breaker_after_max_iterations(self, monkeypatch):
        _setup_workspace()

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "read_memory"
        tool_block.id = "tool_1"
        tool_block.input = {"query": "anything"}

        resp = MagicMock()
        resp.stop_reason = "tool_use"
        resp.content = [tool_block]

        call_count = [0]

        def fake_create(**kwargs):
            call_count[0] += 1
            return resp

        monkeypatch.setattr(marcus_ai.client.messages, "create", fake_create)
        result = agent.run(PHONE, "Loop forever.", heartbeat=False, deep=False)
        assert call_count[0] == agent.MAX_ITERATIONS
        assert "turned around" in result
