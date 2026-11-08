"""Deterministic instruction -> diff fallback for a small closed grammar.

    set title to <text>
    set player <hp|dps> to <number>
    set <encounter|level|asset|scene> <id> <field> to <value>
    add exit from <level> to <level>       | remove exit from <level> to <level>
    add encounter <id> to level <level>    | remove encounter <id> from level <level>
    remove <level|encounter|asset|scene|trigger> <id>

Clauses may be joined with ";" or " and then ". Unknown text -> ``None``.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from .diff import EditOp, PlanDiff

_SECTIONS = {"level": "levels", "encounter": "encounters", "asset": "assets", "scene": "scenes",
             "trigger": "triggers"}
_ID = r"([A-Za-z0-9_.-]+)"
_PATTERNS = (
    (re.compile(r"^set title to (.+)$", re.I), "title"),
    (re.compile(rf"^set player (hp|dps) to ([0-9.]+)$", re.I), "player"),
    (re.compile(rf"^set (encounter|level|asset|scene) {_ID} {_ID} to (.+)$", re.I), "field"),
    (re.compile(rf"^(add|remove) exit from {_ID} to {_ID}$", re.I), "exit"),
    (re.compile(rf"^(add|remove) encounter {_ID} (?:to|from) level {_ID}$", re.I), "level_enc"),
    (re.compile(rf"^remove (level|encounter|asset|scene|trigger) {_ID}$", re.I), "remove"),
)


def _value(text: str) -> Any:
    text = text.strip()
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _clause(c: str) -> list[EditOp] | None:
    for rx, kind in _PATTERNS:
        m = rx.match(c)
        if not m:
            continue
        g = m.groups()
        if kind == "title":
            return [EditOp("change", ("title",), g[0].strip())]
        if kind == "player":
            return [EditOp("change", ("player", g[0].lower()), _value(g[1]))]
        if kind == "field":
            return [EditOp("change", (_SECTIONS[g[0].lower()], g[1], g[2]), _value(g[3]))]
        if kind == "exit":
            path = ("levels", g[1], "exits")
            return [EditOp("add", path, g[2])] if g[0].lower() == "add" else [EditOp("remove", path + (g[2],))]
        if kind == "level_enc":
            path = ("levels", g[2], "encounters")
            return [EditOp("add", path, g[1])] if g[0].lower() == "add" else [EditOp("remove", path + (g[1],))]
        return [EditOp("remove", (_SECTIONS[g[0].lower()], g[1]))]
    return None


def rule_based_diff(instruction: str, plan: Mapping[str, Any] | None = None) -> PlanDiff | None:
    clauses = [c.strip().rstrip(".") for c in re.split(r";|\band then\b", instruction, flags=re.I)]
    ops: list[EditOp] = []
    for c in filter(None, clauses):
        got = _clause(" ".join(c.split()))
        if got is None:
            return None
        ops.extend(got)
    return PlanDiff(tuple(ops)) if ops else None
