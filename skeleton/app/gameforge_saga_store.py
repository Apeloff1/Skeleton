"""Persistent multi-owner saga revision journal."""
from __future__ import annotations

from typing import Any

from skeleton.app.gameforge_campaign_store import CampaignStore
from skeleton.app.gameforge_saga import play_saga, resume_saga, verify_saga


def _verify(source: Any, receipt: Any) -> bool:
    return verify_saga(source, receipt, session=True)


class SagaStore(CampaignStore):
    """The existing transactional owner with fixed stronger saga replay."""

    _namespace = "saga"
    _play = staticmethod(play_saga)
    _verify = staticmethod(_verify)
    _append = staticmethod(resume_saga)
