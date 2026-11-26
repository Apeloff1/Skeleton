"""Durable expedition journal using the same transactional campaign owner.

The namespace and three replay functions are fixed at source level. In
particular, no portable checkpoint can downgrade expedition validation to
the base narrative campaign verifier.
"""
from __future__ import annotations

from typing import Any

from skeleton.app.gameforge_campaign_store import CampaignStore
from skeleton.app.gameforge_expedition import (
    play_expedition, resume_expedition, verify_expedition,
)


def _verify(source: Any, receipt: Any) -> bool:
    return verify_expedition(source, receipt, session=True)


class ExpeditionStore(CampaignStore):
    """Independent namespace; all inherited transitions replay the full expedition."""

    _namespace = "expedition"
    _play = staticmethod(play_expedition)
    _verify = staticmethod(_verify)
    _append = staticmethod(resume_expedition)
