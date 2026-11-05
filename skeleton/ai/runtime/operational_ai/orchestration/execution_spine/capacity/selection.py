"""Deterministic history and source selection without generated summaries."""
from __future__ import annotations
from dataclasses import dataclass
from ..contracts import SpineError
from ..context import Evidence


@dataclass(frozen=True, slots=True)
class Selection:
    history: tuple[dict, ...]
    evidence: tuple[Evidence, ...]
    omitted_turns: int
    omitted_sources: int

    def __post_init__(self):
        if len(self.history) % 2:
            raise SpineError('context selection broke a historical turn')
        if type(self.omitted_turns) is not int or self.omitted_turns < 0:
            raise SpineError('invalid turn omission accounting')
        if type(self.omitted_sources) is not int or self.omitted_sources < 0:
            raise SpineError('invalid evidence omission accounting')


def select_initial(history: tuple[dict, ...], evidence: tuple[Evidence, ...],
                   source_limit: int) -> Selection:
    if type(source_limit) is not int or source_limit < 0:
        raise SpineError('invalid evidence selection limit')
    return Selection(history, evidence[:source_limit], 0,
                     len(evidence) - min(len(evidence), source_limit))


def reduce(selection: Selection) -> Selection | None:
    """Always evict the oldest *complete* turn before the least-ranked source.

    The evidence provider's rank order is authoritative for relevance, not
    factual correctness. The planner never rearranges or invents source text.
    When the history is exhausted, trim least-ranked sources one at a time.
    """
    if selection.history:
        return Selection(selection.history[2:], selection.evidence,
                         selection.omitted_turns + 1, selection.omitted_sources)
    if selection.evidence:
        return Selection(selection.history, selection.evidence[:-1],
                         selection.omitted_turns, selection.omitted_sources + 1)
    return None
