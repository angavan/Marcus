"""
tests/test_workspace.py — Unit tests for workspace.py

Tests file I/O, goal CRUD, timezone extraction, context assembly, and transcript ops.
All tests use a temp directory so they never touch real user data.
"""
from datetime import date
from pathlib import Path

import pytest

import workspace as ws


@pytest.fixture
def tmp_workspace(isolated_workspace):
    """Alias for the shared isolated_workspace fixture."""
    return isolated_workspace


PHONE = "+15550001234"


# ── is_new_user / initialize_workspace ────────────────────────────────────────

def test_is_new_user_before_init(tmp_workspace):
    assert ws.is_new_user(PHONE) is True


def test_initialize_workspace_creates_files(tmp_workspace):
    # Create minimal templates
    tpl_dir = ws.TEMPLATE_DIR
    tpl_dir.mkdir(parents=True, exist_ok=True)
    (tpl_dir / "IDENTITY.md").write_text("# IDENTITY\n[To be filled]")
    (tpl_dir / "MEMORY.md").write_text("# MEMORY\n")

    ws.initialize_workspace(PHONE)

    assert not ws.is_new_user(PHONE)
    assert (ws.user_dir(PHONE) / "IDENTITY.md").exists()
    assert (ws.user_dir(PHONE) / "MEMORY.md").exists()
    assert (ws.user_dir(PHONE) / "memory").is_dir()


# ── read_file / write_file ─────────────────────────────────────────────────────

def test_write_and_read_file(tmp_workspace):
    ws.write_file(PHONE, "TEST.md", "hello world")
    assert ws.read_file(PHONE, "TEST.md") == "hello world"


def test_read_missing_file_returns_empty(tmp_workspace):
    assert ws.read_file(PHONE, "NONEXISTENT.md") == ""


# ── Goal management ────────────────────────────────────────────────────────────

IDENTITY_TEMPLATE = """\
# IDENTITY

## Name
Alice

## Short-Term Goals
- [To be filled]

## Long-Term Goals
- [To be filled]

## Dreams
- [To be filled]
"""


def _setup_identity(content=IDENTITY_TEMPLATE):
    ws.write_file(PHONE, "IDENTITY.md", content)


def test_add_goal_short_term(tmp_workspace):
    _setup_identity()
    ws.add_goal(PHONE, "Ship v1", "Short-Term Goals")
    goals = ws.list_goals(PHONE)
    texts = [g for g, _ in goals]
    assert "Ship v1" in texts


def test_add_goal_removes_placeholder(tmp_workspace):
    _setup_identity()
    ws.add_goal(PHONE, "Ship v1", "Short-Term Goals")
    content = ws.read_file(PHONE, "IDENTITY.md")
    assert "[To be filled]" not in content


def test_add_multiple_goals(tmp_workspace):
    _setup_identity()
    ws.add_goal(PHONE, "Goal A", "Short-Term Goals")
    ws.add_goal(PHONE, "Goal B", "Short-Term Goals")
    goals = dict(ws.list_goals(PHONE))
    assert "Goal A" in goals
    assert "Goal B" in goals


def test_remove_goal(tmp_workspace):
    _setup_identity()
    ws.add_goal(PHONE, "Remove me", "Short-Term Goals")
    ws.remove_goal(PHONE, "Remove me")
    texts = [g for g, _ in ws.list_goals(PHONE)]
    assert "Remove me" not in texts


def test_remove_goal_does_not_remove_others(tmp_workspace):
    _setup_identity()
    ws.add_goal(PHONE, "Keep me", "Short-Term Goals")
    ws.add_goal(PHONE, "Remove me", "Short-Term Goals")
    ws.remove_goal(PHONE, "Remove me")
    texts = [g for g, _ in ws.list_goals(PHONE)]
    assert "Keep me" in texts


def test_list_goals_empty(tmp_workspace):
    _setup_identity()
    assert ws.list_goals(PHONE) == []


def test_add_dream(tmp_workspace):
    _setup_identity()
    ws.add_goal(PHONE, "Write a novel", "Dreams")
    texts = [g for g, _ in ws.list_goals(PHONE)]
    assert "Write a novel" in texts


# ── Timezone extraction ────────────────────────────────────────────────────────

def test_get_timezone_from_identity(tmp_workspace):
    ws.write_file(PHONE, "IDENTITY.md", "## Timezone\nEurope/London\n")
    ws.write_file(PHONE, "USER.md", "")
    assert ws.get_timezone(PHONE) == "Europe/London"


def test_get_timezone_from_user_md(tmp_workspace):
    ws.write_file(PHONE, "IDENTITY.md", "## Name\nAlice\n")
    ws.write_file(PHONE, "USER.md", "## Timezone\nAmerica/New_York\n")
    assert ws.get_timezone(PHONE) == "America/New_York"


def test_get_timezone_fallback_utc(tmp_workspace):
    ws.write_file(PHONE, "IDENTITY.md", "## Name\nAlice\n")
    ws.write_file(PHONE, "USER.md", "## Name\nAlice\n")
    assert ws.get_timezone(PHONE) == "UTC"


def test_get_timezone_invalid_value(tmp_workspace):
    ws.write_file(PHONE, "IDENTITY.md", "## Timezone\nNot/ATimezone\n")
    ws.write_file(PHONE, "USER.md", "")
    assert ws.get_timezone(PHONE) == "UTC"


# ── Memory ─────────────────────────────────────────────────────────────────────

def test_append_and_read_daily_log(tmp_workspace):
    ws.user_dir(PHONE).mkdir(parents=True, exist_ok=True)
    (ws.user_dir(PHONE) / "memory").mkdir(exist_ok=True)
    ws.append_daily_log(PHONE, "Worked on tests today.")
    log = ws.read_daily_log(PHONE)
    assert "Worked on tests today." in log


def test_append_memory(tmp_workspace):
    ws.write_file(PHONE, "MEMORY.md", "# MEMORY\n")
    ws.append_memory(PHONE, "User likes philosophy.")
    content = ws.read_file(PHONE, "MEMORY.md")
    assert "User likes philosophy." in content


# ── Transcripts ────────────────────────────────────────────────────────────────

def test_append_and_load_transcript(tmp_workspace):
    ws.append_transcript(PHONE, "user", "Hello Marcus.")
    ws.append_transcript(PHONE, "assistant", "Greetings.")
    history = ws.load_history(PHONE)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello Marcus."
    assert history[1]["role"] == "assistant"


def test_load_history_limit(tmp_workspace):
    for i in range(30):
        ws.append_transcript(PHONE, "user", f"msg {i}")
    history = ws.load_history(PHONE, limit=10)
    assert len(history) == 10
    assert history[-1]["content"] == "msg 29"


def test_load_history_empty(tmp_workspace):
    assert ws.load_history(PHONE) == []


# ── to_whatsapp ────────────────────────────────────────────────────────────────

def test_to_whatsapp_converts_headings():
    md = "# Title\n## Section\n### Sub\nPlain text"
    result = ws.to_whatsapp(md)
    assert result == "*Title*\n*Section*\n_Sub_\nPlain text"


def test_to_whatsapp_passthrough_plain():
    assert ws.to_whatsapp("just text") == "just text"


# ── assemble_context ───────────────────────────────────────────────────────────

def test_assemble_context_heartbeat_loads_only_heartbeat(tmp_workspace):
    ws.write_file(PHONE, "HEARTBEAT.md", "# Heartbeat checklist\n- check goals")
    ws.write_file(PHONE, "AGENTS.md", "# Agents\nDo not include this.")
    ctx = ws.assemble_context(PHONE, heartbeat=True)
    assert "HEARTBEAT.md" in ctx
    assert "AGENTS.md" not in ctx


def test_assemble_context_full_loads_bootstrap_files(tmp_workspace):
    for f in ["AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md"]:
        ws.write_file(PHONE, f, f"# {f}\ncontent")
    ctx = ws.assemble_context(PHONE, heartbeat=False)
    assert "AGENTS.md" in ctx
    assert "SOUL.md" in ctx
