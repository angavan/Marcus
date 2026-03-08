"""
tests/test_menu.py — Unit tests for the menu state machine.

Tests onboarding flow, menu navigation, and edge inputs.
All Claude API calls are mocked; no real network calls made.
"""
from unittest.mock import MagicMock, patch

import pytest

import memory
import workspace as ws


PHONE = "+15550001234"


def _mock_parse_basics(text):
    return {"name": "Alice", "location": "London"}


def _mock_resolve_timezone(loc):
    return "Europe/London"


def _mock_write_identity(name, tz, answers):
    return f"# IDENTITY\n## Name\n{name}\n## Timezone\n{tz}\n## Short-Term Goals\n- Ship v1\n"


def _mock_agent_run(phone, text, heartbeat=False, deep=False):
    return "Marcus response."


# ── Onboarding ─────────────────────────────────────────────────────────────────

class TestOnboarding:
    @patch("marcus_ai.parse_basics", side_effect=_mock_parse_basics)
    @patch("marcus_ai.resolve_timezone", side_effect=_mock_resolve_timezone)
    def test_new_user_gets_welcome(self, mock_tz, mock_parse):
        import menu
        reply = menu.handle_message(PHONE, "Hello")
        assert "Marcus" in reply
        s = memory.get_session(PHONE)
        assert s["menu_state"] == "setup:basics"

    @patch("marcus_ai.parse_basics", side_effect=_mock_parse_basics)
    @patch("marcus_ai.resolve_timezone", side_effect=_mock_resolve_timezone)
    def test_basics_transitions_to_intake(self, mock_tz, mock_parse):
        import menu
        menu.handle_message(PHONE, "Hello")  # welcome
        reply = menu.handle_message(PHONE, "Alice, London")
        assert "Alice" in reply
        s = memory.get_session(PHONE)
        assert s["menu_state"] == "setup:intake"

    @patch("marcus_ai.parse_basics", return_value={})
    @patch("marcus_ai.resolve_timezone", return_value="UTC")
    def test_basics_empty_input_does_not_crash(self, mock_tz, mock_parse):
        """Sending only spaces should not raise IndexError."""
        import menu
        menu.handle_message(PHONE, "Hello")
        reply = menu.handle_message(PHONE, "   ")
        assert reply  # some response returned without crash

    @patch("marcus_ai.parse_basics", side_effect=_mock_parse_basics)
    @patch("marcus_ai.resolve_timezone", side_effect=_mock_resolve_timezone)
    @patch("marcus_ai.write_identity", side_effect=_mock_write_identity)
    def test_intake_transitions_to_confirm(self, mock_wi, mock_tz, mock_parse):
        import menu
        menu.handle_message(PHONE, "Hi")
        menu.handle_message(PHONE, "Alice, London")
        reply = menu.handle_message(PHONE, "I work in tech. Goals: ship product. Dream: build empire.")
        assert "picture" in reply.lower() or "Identity" in reply or "NAME" in reply.upper() or "Alice" in reply
        s = memory.get_session(PHONE)
        assert s["menu_state"] == "setup:confirm"

    @patch("marcus_ai.parse_basics", side_effect=_mock_parse_basics)
    @patch("marcus_ai.resolve_timezone", side_effect=_mock_resolve_timezone)
    @patch("marcus_ai.write_identity", side_effect=_mock_write_identity)
    @patch("scheduler.schedule_user")
    def test_confirm_yes_completes_onboarding(self, mock_sched, mock_wi, mock_tz, mock_parse):
        import menu
        menu.handle_message(PHONE, "Hi")
        menu.handle_message(PHONE, "Alice, London")
        menu.handle_message(PHONE, "Intake answers here.")
        reply = menu.handle_message(PHONE, "looks good")
        assert "saved" in reply.lower() or "Alice" in reply
        s = memory.get_session(PHONE)
        assert s["menu_state"] is None


# ── Global shortcuts ───────────────────────────────────────────────────────────

class TestGlobalShortcuts:
    def _onboard(self):
        """Get user past onboarding quickly."""
        memory.create_session(PHONE)
        ws.initialize_workspace(PHONE)
        ws.write_file(PHONE, "IDENTITY.md", "## Name\nAlice\n## Timezone\nUTC\n")
        memory.set_menu_state(PHONE, None)

    def test_menu_keyword_shows_main_menu(self):
        import menu
        self._onboard()
        reply = menu.handle_message(PHONE, "menu")
        assert "MARCUS" in reply or "Chat freely" in reply

    def test_help_keyword_shows_help(self):
        import menu
        self._onboard()
        reply = menu.handle_message(PHONE, "help")
        assert "Help" in reply or "menu" in reply.lower()

    def test_home_keyword_shows_main_menu(self):
        import menu
        self._onboard()
        reply = menu.handle_message(PHONE, "home")
        assert "MARCUS" in reply or "Chat freely" in reply

    def test_zero_from_submenu_returns_to_main(self):
        import menu
        self._onboard()
        memory.set_menu_state(PHONE, "goals:main")
        reply = menu.handle_message(PHONE, "0")
        assert "MARCUS" in reply or "Chat freely" in reply


# ── Goals menu ─────────────────────────────────────────────────────────────────

class TestGoalsMenu:
    def _setup(self):
        memory.create_session(PHONE)
        ws.initialize_workspace(PHONE)
        ws.write_file(PHONE, "IDENTITY.md",
            "# IDENTITY\n## Name\nAlice\n## Timezone\nUTC\n"
            "## Short-Term Goals\n- [To be filled]\n"
            "## Long-Term Goals\n- [To be filled]\n"
            "## Dreams\n- [To be filled]\n"
        )
        memory.set_menu_state(PHONE, "goals:main")

    def test_view_goals_option(self):
        import menu
        self._setup()
        ws.add_goal(PHONE, "Ship v1", "Short-Term Goals")
        reply = menu.handle_message(PHONE, "1")
        assert "Ship v1" in reply

    def test_add_goal_flow(self):
        import menu
        self._setup()
        menu.handle_message(PHONE, "2")  # add goal
        menu.handle_message(PHONE, "Build a company")  # goal text
        reply = menu.handle_message(PHONE, "1")  # short-term
        assert "Build a company" in reply or "Short" in reply

    def test_add_dream_flow(self):
        import menu
        self._setup()
        menu.handle_message(PHONE, "4")  # add dream
        reply = menu.handle_message(PHONE, "Travel the world")
        assert "Travel the world" in reply

    def test_remove_goal_flow(self):
        import menu
        self._setup()
        ws.add_goal(PHONE, "Remove this goal", "Short-Term Goals")
        menu.handle_message(PHONE, "3")  # remove goal
        reply = menu.handle_message(PHONE, "1")  # remove first
        assert "Removed" in reply or "Remove this goal" in reply

    def test_remove_with_no_goals(self):
        import menu
        self._setup()  # Fresh IDENTITY.md with only placeholder goals — list_goals returns []
        reply = menu.handle_message(PHONE, "3")
        assert "no goals" in reply.lower()


# ── Settings menu ──────────────────────────────────────────────────────────────

class TestSettingsMenu:
    def _setup(self):
        memory.create_session(PHONE)
        ws.initialize_workspace(PHONE)
        ws.write_file(PHONE, "IDENTITY.md",
            "# IDENTITY\n## Name\nAlice\n## Timezone\nUTC\n## Occupation\nEngineer\n"
        )
        memory.set_menu_state(PHONE, "settings:main")

    def test_update_name(self):
        import menu
        self._setup()
        menu.handle_message(PHONE, "1")
        reply = menu.handle_message(PHONE, "Bob")
        assert "Bob" in reply

    def test_update_name_empty_input(self):
        import menu
        self._setup()
        menu.handle_message(PHONE, "1")
        reply = menu.handle_message(PHONE, "   ")
        assert reply  # no crash, prompts again

    @patch("marcus_ai.resolve_timezone", return_value="America/New_York")
    @patch("scheduler.reschedule_user")
    def test_update_timezone(self, mock_sched, mock_tz):
        import menu
        self._setup()
        menu.handle_message(PHONE, "2")
        reply = menu.handle_message(PHONE, "New York")
        assert "America/New_York" in reply

    def test_update_occupation(self):
        import menu
        self._setup()
        menu.handle_message(PHONE, "3")
        reply = menu.handle_message(PHONE, "Founder")
        assert "Founder" in reply

    def test_update_interests(self):
        import menu
        self._setup()
        menu.handle_message(PHONE, "4")
        reply = menu.handle_message(PHONE, "Stoicism, Running, Books")
        assert "Stoicism" in reply or "interests" in reply.lower()


# ── Chat handler ───────────────────────────────────────────────────────────────

class TestChatHandler:
    def _setup(self):
        memory.create_session(PHONE)
        ws.initialize_workspace(PHONE)
        ws.write_file(PHONE, "IDENTITY.md", "## Name\nAlice\n## Timezone\nUTC\n")
        memory.set_menu_state(PHONE, None)

    @patch("agent.run", return_value="Here is my response.")
    def test_regular_chat_routes_to_agent(self, mock_run):
        import menu
        self._setup()
        reply = menu.handle_message(PHONE, "What is virtue?")
        mock_run.assert_called_once_with(PHONE, "What is virtue?", heartbeat=False, deep=False)
        assert reply == "Here is my response."

    @patch("agent.run", return_value="Deep analysis here.")
    def test_deep_prefix_sets_deep_flag(self, mock_run):
        import menu
        self._setup()
        menu.handle_message(PHONE, "deep: Analyse my quarterly goals")
        mock_run.assert_called_once_with(PHONE, "Analyse my quarterly goals", heartbeat=False, deep=True)

    @patch("agent.run", return_value=None)
    def test_none_reply_returns_fallback(self, mock_run):
        import menu
        self._setup()
        reply = menu.handle_message(PHONE, "Hello")
        assert reply == "I have nothing to add."
