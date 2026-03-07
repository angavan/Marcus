"""
workspace.py — Workspace kernel: Markdown file-based identity, memory, and transcripts.

Directory layout per user:
  workspace/<phone>/
    AGENTS.md       — operating contract (static, loaded every session)
    SOUL.md         — Marcus's character (static)
    IDENTITY.md     — user profile, goals, values (updated by Marcus)
    USER.md         — preferences and schedule notes
    MEMORY.md       — long-term memory (appended by Marcus)
    HEARTBEAT.md    — periodic check checklist
    memory/
      YYYY-MM-DD.md — daily working memory logs

Transcripts (immutable JSONL audit trail):
  transcripts/<phone>.jsonl
"""
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pytz

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = Path("workspace")
SKILL_ROOT = Path("skills")
TRANSCRIPT_ROOT = Path("transcripts")
TEMPLATE_DIR = WORKSPACE_ROOT / "_templates"

# Loaded into every full session (order matters — later files can reference earlier ones)
BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md"]

MAX_FILE_CHARS = 20_000   # per file
MAX_TOTAL_CHARS = 150_000  # total context budget


# ── Directory helpers ──────────────────────────────────────────────────────────

def user_dir(phone: str) -> Path:
    return WORKSPACE_ROOT / phone.lstrip("+").replace(" ", "_")


def is_new_user(phone: str) -> bool:
    return not (user_dir(phone) / "IDENTITY.md").exists()


def initialize_workspace(phone: str):
    """Copy template files into a new user's workspace directory."""
    dest = user_dir(phone)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "memory").mkdir(exist_ok=True)
    for template in TEMPLATE_DIR.glob("*.md"):
        target = dest / template.name
        if not target.exists():
            target.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    logger.info("Workspace initialized for %s", phone)


# ── File I/O ───────────────────────────────────────────────────────────────────

def read_file(phone: str, filename: str) -> str:
    path = user_dir(phone) / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:MAX_FILE_CHARS]


def write_file(phone: str, filename: str, content: str):
    d = user_dir(phone)
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text(content, encoding="utf-8")


# ── Memory ─────────────────────────────────────────────────────────────────────

def read_daily_log(phone: str, dt: Optional[date] = None) -> str:
    return read_file(phone, f"memory/{(dt or date.today()).isoformat()}.md")


def append_daily_log(phone: str, entry: str):
    path = user_dir(phone) / f"memory/{date.today().isoformat()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n## {datetime.now().strftime('%H:%M')}\n{entry}\n")


def append_memory(phone: str, note: str):
    """Append a permanent note to MEMORY.md."""
    existing = read_file(phone, "MEMORY.md")
    updated = f"{existing}\n\n### {date.today().isoformat()}\n{note}".strip()
    write_file(phone, "MEMORY.md", updated)


# ── Goal management ────────────────────────────────────────────────────────────

def list_goals(phone: str) -> list[tuple[str, str]]:
    """Return [(goal_text, section_header), ...] from IDENTITY.md."""
    content = read_file(phone, "IDENTITY.md")
    result = []
    for m in re.finditer(
        r"## (Short-Term Goals|Long-Term Goals|Dreams)\n(.*?)(?=\n##|\Z)", content, re.DOTALL
    ):
        section = m.group(1)
        for line in m.group(2).strip().splitlines():
            goal = line.lstrip("- •").strip()
            if goal and goal not in ("[To be filled]", "(none)"):
                result.append((goal, section))
    return result


def add_goal(phone: str, goal_text: str, section_header: str):
    content = read_file(phone, "IDENTITY.md")
    target = f"## {section_header}\n"
    if target in content:
        content = content.replace(target, f"{target}- {goal_text}\n", 1)
        content = content.replace("- [To be filled]\n", "").replace("- (none)\n", "")
    else:
        content += f"\n\n## {section_header}\n- {goal_text}"
    write_file(phone, "IDENTITY.md", content)


def remove_goal(phone: str, goal_text: str):
    content = read_file(phone, "IDENTITY.md")
    write_file(phone, "IDENTITY.md", content.replace(f"- {goal_text}\n", ""))


# ── Timezone ───────────────────────────────────────────────────────────────────

def get_timezone(phone: str) -> str:
    """Extract timezone from IDENTITY.md or USER.md; fallback to UTC."""
    for filename in ("USER.md", "IDENTITY.md"):
        content = read_file(phone, filename)
        m = re.search(r"## Timezone\s*\n([^\n#]+)", content)
        if m:
            tz = m.group(1).strip()
            if tz in pytz.all_timezones:
                return tz
    return "UTC"


# ── Context assembly ───────────────────────────────────────────────────────────

def assemble_context(phone: str, heartbeat: bool = False) -> str:
    """Build system prompt from workspace files. Heartbeat mode loads only HEARTBEAT.md."""
    files = ["HEARTBEAT.md"] if heartbeat else BOOTSTRAP_FILES
    parts, total = [], 0
    for filename in files:
        content = read_file(phone, filename)
        if content:
            parts.append(f"<!-- {filename} -->\n{content}")
            total += len(content)
            if total >= MAX_TOTAL_CHARS:
                break
    if not heartbeat:
        daily = read_daily_log(phone)
        if daily:
            parts.append(f"<!-- Today's Log -->\n{daily[:MAX_FILE_CHARS]}")
    return "\n\n---\n\n".join(parts)


def skill_summaries() -> str:
    """Compact list of available skill names + descriptions for context injection."""
    if not SKILL_ROOT.exists():
        return ""
    lines = []
    for skill_dir in sorted(SKILL_ROOT.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        desc, in_front = "", False
        for line in skill_file.read_text(encoding="utf-8").splitlines():
            if line.strip() == "---":
                in_front = not in_front
            elif in_front and line.startswith("description:"):
                desc = line.split(":", 1)[1].strip().strip("\"'")
                break
        lines.append(f"- `{skill_dir.name}`: {desc}")
    return "\n".join(lines)


# ── JSONL transcripts ──────────────────────────────────────────────────────────

def append_transcript(phone: str, role: str, content: str):
    TRANSCRIPT_ROOT.mkdir(exist_ok=True)
    path = TRANSCRIPT_ROOT / f"{phone.lstrip('+').replace(' ', '_')}.jsonl"
    entry = json.dumps({"role": role, "content": content, "ts": datetime.utcnow().isoformat()})
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def load_history(phone: str, limit: int = 20) -> list[dict]:
    path = TRANSCRIPT_ROOT / f"{phone.lstrip('+').replace(' ', '_')}.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    result = []
    for line in lines[-limit:]:
        try:
            e = json.loads(line)
            result.append({"role": e["role"], "content": e["content"]})
        except Exception:
            pass
    return result


# ── WhatsApp Markdown formatting ───────────────────────────────────────────────

def to_whatsapp(content: str) -> str:
    """Convert Markdown headings to WhatsApp-safe bold text."""
    lines = []
    for line in content.splitlines():
        if line.startswith("### "):
            lines.append(f"_{line[4:]}_")
        elif line.startswith("## "):
            lines.append(f"*{line[3:]}*")
        elif line.startswith("# "):
            lines.append(f"*{line[2:]}*")
        else:
            lines.append(line)
    return "\n".join(lines)
