"""Trusted acquisition-to-Dragon bridge for the three idle-only gatherers.

The *host* owns the physical fetch, video grant, DNS/robots/terms/copyright
checks, cancellation deadlines and independent human-review record. This module
only checks capture identity and routes real authorized canonical custody
through DragonFamilyCustodyBridge into the durable idle coordinator.

There is no public API that can create captures, start crawling or mint XP.
The three supplied callbacks return captured source evidence or None (not
changed), never raw user-submitted approvals or model weights.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .core import CrawlDocument
from .dragon_family import IdleWindow, SourceReceipt, _tokens
from .dragon_family_custody_bridge import (
    ApprovedSourceSnapshot, DragonFamilyCustodyBridge,
)
from .dragon_family_idle_coordinator import (
    DragonIdleCoordinator, IdleCoordinatorPolicy, IdleTask,
)
from .video_digest import VideoKnowledgeChunk


@dataclass(frozen=True)
class AcquiredArticle:
    snapshot: ApprovedSourceSnapshot
    document: CrawlDocument


@dataclass(frozen=True)
class AcquiredVideo:
    snapshot: ApprovedSourceSnapshot
    chunks: tuple[VideoKnowledgeChunk, ...]


Acquired = AcquiredArticle | AcquiredVideo | None
CaptureAdapter = Callable[[IdleTask], Acquired]


class DragonIdleAcquisitionService:
    """Owner-locked glue between the existing producer and idle hatchlings.

    Register functions only from an authenticated, policy-bound producer that
    can independently confirm capture, source license, user consent and human
    review. The service never accepts a SourceReceipt from an untrusted caller.
    """

    def __init__(self, bridge: DragonFamilyCustodyBridge,
                 *, policy: IdleCoordinatorPolicy = IdleCoordinatorPolicy()):
        if not isinstance(bridge, DragonFamilyCustodyBridge):
            raise PermissionError("canonical Dragon custody bridge required")
        self.bridge = bridge
        self.coordinator = DragonIdleCoordinator(bridge.family(), policy=policy)

    def _receipt(self, task: IdleTask, item: Acquired) -> SourceReceipt | None:
        if item is None:
            return None
        if not isinstance(item, (AcquiredArticle,AcquiredVideo)):
            raise ValueError("host must return an independently reviewed real capture")
        snapshot = item.snapshot
        if not isinstance(snapshot, ApprovedSourceSnapshot):
            raise ValueError("acquired media missing canonical snapshot")
        # Enforce immutable registered source identity and scope on *every*
        # adapter, including the cross-media revision monitor.
        if (snapshot.source_id != task.source_id or
                snapshot.url != task.url or
                snapshot.media != task.media or
                _tokens(snapshot.topics) != _tokens(task.topics)):
            raise PermissionError("captured source not bound to idle work lease")
        if task.dragon == "article" and not isinstance(item,AcquiredArticle):
            raise ValueError("article dragon received non-article evidence")
        if task.dragon == "video" and not isinstance(item,AcquiredVideo):
            raise ValueError("video dragon received non-video evidence")
        if isinstance(item,AcquiredArticle):
            if snapshot.media != "article":
                raise ValueError("article evidence mislabeled")
            seed,receipt=self.bridge.article(snapshot,item.document)
        else:
            if snapshot.media != "video":
                raise ValueError("video evidence mislabeled")
            seed,receipt=self.bridge.video(snapshot,item.chunks)
        if (seed.source_id != task.source_id or seed.url != task.url or
                seed.media != task.media):
            raise PermissionError("reviewed capture changed registered source identity")
        return receipt

    def run_once(self, *,
                 authorized: bool,
                 idle_state: Callable[[], IdleWindow],
                 article_capture: CaptureAdapter | None = None,
                 video_capture: CaptureAdapter | None = None,
                 monitor_capture: CaptureAdapter | None = None,
                 task_topics: tuple[str, ...],
                 adjacent_topics: tuple[str, ...] = ()) -> dict[str, object]:
        """One authorized idle tick; not a daemon, scheduled timer or fetcher."""
        callbacks = {
            "article": article_capture,
            "video": video_capture,
            "monitor": monitor_capture,
        }
        adapters={}
        for role, callback in callbacks.items():
            if callback is None:
                continue
            if not callable(callback):
                raise ValueError("invalid trusted acquisition adapter")
            def adapter(task: IdleTask, *, _callback=callback):
                return self._receipt(task,_callback(task))
            adapters[role]=adapter
        return self.coordinator.run_once(
            self.bridge.owner,authorized=authorized,idle_state=idle_state,
            gatherers=adapters,task_topics=task_topics,
            adjacent_topics=adjacent_topics)

    def health(self, *, authorized: bool) -> dict[str,object]:
        """Owner-locked read of last known attempts; never live-device proof."""
        return self.coordinator.health(self.bridge.owner,authorized=authorized)
