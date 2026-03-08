"""
tests/test_memory.py — Unit tests for memory.py (SQLite session state)
"""
import os
import tempfile

import pytest

import memory




PHONE = "+15550001234"
PHONE2 = "+15550005678"


# ── Session lifecycle ──────────────────────────────────────────────────────────

def test_get_session_missing_returns_none():
    assert memory.get_session(PHONE) is None


def test_create_session_returns_session():
    s = memory.create_session(PHONE)
    assert s is not None
    assert s["phone"] == PHONE


def test_session_has_default_schedule():
    memory.create_session(PHONE)
    s = memory.get_session(PHONE)
    assert s["schedule"]["morning_time"] == "07:00"
    assert s["schedule"]["morning_enabled"] is True


def test_create_session_idempotent_via_get():
    memory.create_session(PHONE)
    s1 = memory.get_session(PHONE)
    s2 = memory.get_session(PHONE)
    assert s1["phone"] == s2["phone"]


# ── Menu state ─────────────────────────────────────────────────────────────────

def test_set_and_get_menu_state():
    memory.create_session(PHONE)
    memory.set_menu_state(PHONE, "goals:main")
    s = memory.get_session(PHONE)
    assert s["menu_state"] == "goals:main"


def test_set_menu_state_with_data():
    memory.create_session(PHONE)
    memory.set_menu_state(PHONE, "setup:intake", {"name": "Alice", "timezone": "UTC"})
    s = memory.get_session(PHONE)
    assert s["menu_state"] == "setup:intake"
    assert s["menu_state_data"]["name"] == "Alice"


def test_clear_menu_state():
    memory.create_session(PHONE)
    memory.set_menu_state(PHONE, "goals:main")
    memory.set_menu_state(PHONE, None)
    s = memory.get_session(PHONE)
    assert s["menu_state"] is None


# ── Schedule ───────────────────────────────────────────────────────────────────

def test_update_schedule():
    memory.create_session(PHONE)
    new_schedule = {**memory.DEFAULT_SCHEDULE, "morning_time": "06:30"}
    memory.update_schedule(PHONE, new_schedule)
    s = memory.get_session(PHONE)
    assert s["schedule"]["morning_time"] == "06:30"


def test_schedule_toggle():
    memory.create_session(PHONE)
    sched = memory.get_session(PHONE)["schedule"]
    sched["morning_enabled"] = False
    memory.update_schedule(PHONE, sched)
    s = memory.get_session(PHONE)
    assert s["schedule"]["morning_enabled"] is False


# ── Message count ──────────────────────────────────────────────────────────────

def test_increment_msg():
    memory.create_session(PHONE)
    c1 = memory.increment_msg(PHONE)
    c2 = memory.increment_msg(PHONE)
    assert c1 == 1
    assert c2 == 2


# ── get_all_sessions ───────────────────────────────────────────────────────────

def test_get_all_sessions():
    memory.create_session(PHONE)
    memory.create_session(PHONE2)
    sessions = memory.get_all_sessions()
    phones = {s["phone"] for s in sessions}
    assert PHONE in phones
    assert PHONE2 in phones


def test_get_all_sessions_empty():
    assert memory.get_all_sessions() == []
