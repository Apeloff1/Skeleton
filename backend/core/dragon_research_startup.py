"""Trusted application opt-in for Dragon's read-only research dashboard.

This wiring does not create a research vault, seed keys, or accept caller
configuration. Unconfigured installations keep the router fail-closed (503).
"""
from __future__ import annotations

import os
from fastapi import FastAPI

from core.dragon_research_session import DragonResearchSessionFactory
from routes.dragon_research import install_dragon_research_dashboard


def configure_dragon_research_dashboard(app: FastAPI) -> bool:
    """Install exactly one operator-controlled, independently keyed dashboard.

    The only enabling value is `1`; misspellings fail startup rather than
    silently pretending the dashboard was enabled.
    """
    enabled = os.environ.get("SKL_DRAGON_RESEARCH_DASHBOARD_ENABLED", "0")
    if enabled in ("", "0"):
        return False
    if enabled != "1":
        raise ValueError("SKL_DRAGON_RESEARCH_DASHBOARD_ENABLED must be 0 or 1")
    if getattr(app.state, "dragon_research_dashboard", None) is not None:
        raise ValueError("Dragon research dashboard already installed")
    factory = DragonResearchSessionFactory.from_env()
    install_dragon_research_dashboard(app, factory)
    return True
