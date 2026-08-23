"""Sleep-cycle memory consolidation — idle-time replay, decay, and abstraction.

Biological brains do not learn during experience; they learn during sleep,
replaying episodes, strengthening salient traces, letting noise decay, and
compressing repeated patterns into semantic knowledge. The Dream engine gives
the memory trinity the same cycle:

  1. **Replay** — high-importance episodes are re-queried through MAG, which
     increments their access counts (rehearsal bonus on the forgetting curve).
  2. **Decay sweep** — episodes whose retrieval probability has fallen below
     the floor are pruned rather than left to pollute recall.
  3. **Abstraction** — clusters of episodes sharing tags are compressed into a
     single semantic summary chunk written into RAG: episodic detail becomes
     durable fact. This is the hippocampal→neocortical transfer, in code.

The engine never runs inline with user traffic. It is invoked by the agent
scheduler during idle windows, publishes every transition to the event bus,
and is fully deterministic given the same inputs (seedable jitter included
for replay ordering only).
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.memory.types import MemoryChunk
from skeleton.memory.mag import MAGStore
from skeleton.memory.store import MemoryStore


@dataclass
class DreamReport:
    """What one sleep cycle did, for audit and telemetry."""
    started_at: float = field(default_factory=time.time)
    episodes_replayed: int = 0
    episodes_pruned: int = 0
    abstractions_written: int = 0
    tags_clustered: int = 0
    duration_s: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episodes_replayed": self.episodes_replayed,
            "episodes_pruned": self.episodes_pruned,
            "abstractions_written": self.abstractions_written,
            "tags_clustered": self.tags_clustered,
            "duration_s": self.duration_s,
        }


class DreamEngine:
    """
    Idle-time consolidation over MAG (episodic) → RAG (semantic).

    Parameters
    ----------
    replay_top_k:
        How many salient episodes get rehearsed per cycle.
    prune_floor:
        Retrieval-probability floor; episodes below it are deleted.
    cluster_min:
        Minimum episodes sharing a tag before an abstraction is formed.
    """

    def __init__(
        self,
        mag: MAGStore,
        rag: MemoryStore,
        *,
        bus: Optional[EventBus] = None,
        replay_top_k: int = 10,
        prune_floor: float = 0.05,
        cluster_min: int = 3,
        seed: Optional[int] = None,
    ) -> None:
        self._mag = mag
        self._rag = rag
        self._bus = bus
        self.replay_top_k = replay_top_k
        self.prune_floor = prune_floor
        self.cluster_min = cluster_min
        self._rng = random.Random(seed)
        self.cycles_completed = 0

    # ------------------------------------------------------------------
    # The sleep cycle
    # ------------------------------------------------------------------

    def sleep(self) -> DreamReport:
        """Run one full consolidation cycle. Returns an audit report."""
        report = DreamReport()
        start = time.time()
        now = time.time()

        episodes = list(self._mag._episodes.values())

        # ---- Phase 1: replay the salient ---------------------------------
        ranked = sorted(
            episodes,
            key=lambda e: e.compute_retrieval_probability(now),
            reverse=True,
        )
        replay_pool = ranked[: self.replay_top_k]
        self._rng.shuffle(replay_pool)  # biological replay is non-sequential
        for ep in replay_pool:
            # Rehearsal: a MAG query touching the episode bumps access_count,
            # which compounds into its retrieval probability (spacing effect).
            self._mag.query(ep.content, top_k=1)
            report.episodes_replayed += 1

        # ---- Phase 2: decay sweep ----------------------------------------
        doomed = [
            ep.episode_id
            for ep in episodes
            if ep.compute_retrieval_probability(now) < self.prune_floor
        ]
        for eid in doomed:
            if self._mag.delete(eid):
                report.episodes_pruned += 1

        # ---- Phase 3: abstraction (episodic → semantic) -------------------
        clusters: Dict[str, List[str]] = {}
        for ep in self._mag._episodes.values():
            for tag in ep.tags:
                clusters.setdefault(tag, []).append(ep.content)

        report.tags_clustered = sum(1 for c in clusters.values() if len(c) >= self.cluster_min)
        for tag, contents in clusters.items():
            if len(contents) < self.cluster_min:
                continue
            summary = self._abstract(tag, contents)
            chunk = MemoryChunk(
                id=f"dream_{tag}_{hashlib.sha256(summary.encode()).hexdigest()[:12]}",
                text=summary,
                metadata={"tier": "rag", "dream_abstracted": True, "source_tag": tag,
                          "episode_count": len(contents)},
                source_tier="rag",
                confidence=0.9,
            )
            self._rag.add(chunk)
            report.abstractions_written += 1

        report.duration_s = time.time() - start
        self.cycles_completed += 1

        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="memory.dream.cycle_complete",
                    payload=report.to_dict() | {"cycle": self.cycles_completed},
                    correlation_id=f"dream_{self.cycles_completed}",
                )
            )
        return report

    # ------------------------------------------------------------------
    # Abstraction
    # ------------------------------------------------------------------

    def _abstract(self, tag: str, contents: List[str]) -> str:
        """
        Compress a tag cluster into one semantic statement.

        Deliberately simple and lossless-auditable: salient terms are the
        highest document-frequency words across the cluster; the summary
        records them plus provenance. A generative summariser can replace
        this later without changing the contract.
        """
        freq: Dict[str, int] = {}
        for text in contents:
            for word in set(text.lower().split()):
                if len(word) > 3:
                    freq[word] = freq.get(word, 0) + 1
        salient = sorted(freq, key=lambda w: freq[w], reverse=True)[:8]
        return (
            f"[Consolidated knowledge about '{tag}' — distilled from "
            f"{len(contents)} episodes across sleep cycle {self.cycles_completed + 1}. "
            f"Salient concepts: {', '.join(salient)}.]"
        )
