"""
conftest.py — Shared test fixtures.
"""
import pytest
import workspace as ws
import memory


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    """
    Redirect workspace and transcript I/O to a temp dir for every test.
    Also re-initialise the SQLite DB so tests are fully isolated.
    """
    monkeypatch.setattr(ws, "WORKSPACE_ROOT", tmp_path / "workspace")
    monkeypatch.setattr(ws, "TRANSCRIPT_ROOT", tmp_path / "transcripts")
    monkeypatch.setattr(ws, "TEMPLATE_DIR", tmp_path / "workspace" / "_templates")
    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "test.db"))

    (tmp_path / "workspace").mkdir()
    (tmp_path / "transcripts").mkdir()

    # Minimal templates
    tpl = tmp_path / "workspace" / "_templates"
    tpl.mkdir(parents=True)
    (tpl / "IDENTITY.md").write_text("# IDENTITY\n## Name\n[To be filled]\n")
    (tpl / "MEMORY.md").write_text("# MEMORY\n")
    (tpl / "AGENTS.md").write_text("# AGENTS\n")
    (tpl / "SOUL.md").write_text("# SOUL\n")
    (tpl / "USER.md").write_text("# USER\n## Timezone\n[To be filled during onboarding]\n")
    (tpl / "HEARTBEAT.md").write_text("# HEARTBEAT\n")

    memory.init_db()
    yield tmp_path
