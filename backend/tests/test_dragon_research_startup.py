"""Operator-only installation of the read-only Dragon research dashboard."""
from __future__ import annotations

import sqlite3
from fastapi import FastAPI
import pytest

from core.dragon_research_startup import configure_dragon_research_dashboard
from core.dragon_research_session import DragonResearchSessionFactory


def test_dashboard_defaults_to_disabled_and_has_no_implicit_database(monkeypatch, tmp_path):
    monkeypatch.delenv("SKL_DRAGON_RESEARCH_DASHBOARD_ENABLED", raising=False)
    app = FastAPI()
    assert configure_dragon_research_dashboard(app) is False
    assert getattr(app.state, "dragon_research_dashboard", None) is None
    assert list(tmp_path.iterdir()) == []


def test_invalid_enable_value_fails_closed(monkeypatch):
    monkeypatch.setenv("SKL_DRAGON_RESEARCH_DASHBOARD_ENABLED", "true")
    with pytest.raises(ValueError, match="must be 0 or 1"):
        configure_dragon_research_dashboard(FastAPI())


def test_opt_in_without_canonical_store_or_secrets_fails(monkeypatch):
    monkeypatch.setenv("SKL_DRAGON_RESEARCH_DASHBOARD_ENABLED", "1")
    for name in (
        "SKL_DRAGON_KNOWLEDGE_DB_PATH",
        "SKL_DRAGON_PRACTICE_DB_PATH",
        "SKL_DRAGON_NEST_SIGNING_KEY_HEX",
        "SKL_DRAGON_TRANSCRIPT_REVIEW_PUBLIC_KEY_HEX",
        "SKL_DRAGON_TRANSCRIPT_REVIEW_ISSUER",
        "SKL_DRAGON_TRANSCRIPT_REVIEW_KEY_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    app = FastAPI()
    with pytest.raises((ValueError, TypeError)):
        configure_dragon_research_dashboard(app)
    assert getattr(app.state, "dragon_research_dashboard", None) is None


def test_explicit_valid_opt_in_uses_existing_operator_store(monkeypatch, tmp_path):
    knowledge = tmp_path / "knowledge.sqlite"
    nest = tmp_path / "nest.sqlite"
    for path in (knowledge, nest):
        with sqlite3.connect(path):
            pass
    monkeypatch.setenv("SKL_DRAGON_RESEARCH_DASHBOARD_ENABLED", "1")
    monkeypatch.setenv("SKL_DRAGON_KNOWLEDGE_DB_PATH", str(knowledge))
    monkeypatch.setenv("SKL_DRAGON_PRACTICE_DB_PATH", str(nest))
    monkeypatch.setenv("SKL_DRAGON_NEST_SIGNING_KEY_HEX", ("ac" * 32))
    monkeypatch.setenv("SKL_DRAGON_TRANSCRIPT_REVIEW_PUBLIC_KEY_HEX", ("bc" * 32))
    monkeypatch.setenv("SKL_DRAGON_TRANSCRIPT_REVIEW_ISSUER", "operator-reviewer")
    monkeypatch.setenv("SKL_DRAGON_TRANSCRIPT_REVIEW_KEY_ID", "review-key-v1")
    app = FastAPI()
    assert configure_dragon_research_dashboard(app) is True
    assert isinstance(app.state.dragon_research_dashboard, DragonResearchSessionFactory)
    with pytest.raises(ValueError, match="already"):
        configure_dragon_research_dashboard(app)
