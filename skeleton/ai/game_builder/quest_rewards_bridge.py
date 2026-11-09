"""Route Director quest completion into an economy reward faucet.

The reward authority is Murash's B028 ``QuestBoard``
(``skeleton/economy/gameplay/quests.py``, draft PR #4598, not merged).  It
is deliberately *not imported*: :class:`QuestRewardBoard` mirrors the two
public methods this bridge needs, so any object with that shape (B028 once
merged, or a test double) plugs in.

B028 semantics relied on: ``complete`` pays all-or-nothing and raises (its
``EconomySimError``, a ``ValueError``) on repeat, missing prerequisites,
full inventory or faucet refusal; on success it returns
``{"money": int, "items": {item_id: qty}}``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from skeleton.frontier.progression.quests import QuestProgressState


@runtime_checkable
class QuestRewardBoard(Protocol):
    """Mirror of B028 ``QuestBoard``'s public API (#4598)."""

    def completed(self, owner: str, quest_id: str) -> bool: ...

    def complete(self, owner: str, quest_id: str, tick: int) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class RewardOutcome:
    quest_id: str
    status: str  # "paid" | "already_paid" | "not_complete" | "failed" | "refused"
    money: int = 0
    items: Mapping[str, int] = field(default_factory=dict)
    reason: str = ""


class QuestRewardBridge:
    def __init__(self, board: QuestRewardBoard, *,
                 refusals: tuple[type[BaseException], ...] = (ValueError,)) -> None:
        if not isinstance(board, QuestRewardBoard):
            raise TypeError("board must provide completed() and complete()")
        self.board = board
        self.refusals = refusals

    def claim(self, owner: str, progress: QuestProgressState, tick: int) -> RewardOutcome:
        qid = progress.quest_id
        if progress.status == "failed":
            return RewardOutcome(qid, "failed", reason="quest failed")
        if not progress.completed:
            return RewardOutcome(qid, "not_complete", reason="objectives outstanding")
        if self.board.completed(owner, qid):
            return RewardOutcome(qid, "already_paid")
        try:
            paid = self.board.complete(owner, qid, tick)
        except self.refusals as exc:
            return RewardOutcome(qid, "refused", reason=str(exc))
        return RewardOutcome(qid, "paid", int(paid.get("money", 0)),
                             dict(paid.get("items", {})))


__all__ = ["QuestRewardBoard", "QuestRewardBridge", "RewardOutcome"]
