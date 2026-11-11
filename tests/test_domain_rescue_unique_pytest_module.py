"""Distinct domain rescue suites must collect as distinct pytest modules.

Avoid pytest's import-file mismatch when independent directories are not Python
packages; preserve both original suites, not skip or ignore either domain.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_rescue_suites_use_distinct_modules_without_skipping_domain_tests():
    original_dialogue = ROOT / "skeleton/testing/dialogue_sessions_v1/test_companions_rescue.py"
    renamed_quest = ROOT / "skeleton/testing/questflows_v1/test_questflows_companions_rescue.py"
    conflicting_quest = ROOT / "skeleton/testing/questflows_v1/test_companions_rescue.py"
    assert original_dialogue.is_file()
    assert renamed_quest.is_file()
    assert not conflicting_quest.exists()
    assert "def test_" in original_dialogue.read_text(encoding="utf-8")
    assert "def test_" in renamed_quest.read_text(encoding="utf-8")
