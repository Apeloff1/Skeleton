"""Natural-language iterative repair for creator design graphs (#807 B020).

A user describes a defect or change in plain words. B020 turns the request
into a small, bounded list of typed repair operations, applies them to a copy
of the current B012 design graph, previews the result as a B016 semantic diff,
runs the caller's checks, and only then lets the change be accepted into the
B018 generated-state history, where it can be rolled back exactly.

Parsing is deterministic and rule-based: no model calls, no network, no code
execution. Anything the parser cannot resolve to exactly one graph entity is
rejected with a reason instead of guessed. Nothing is applied until
:func:`accept_repair` is called with a proposal whose evidence still matches.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Callable, Iterable, NoReturn, Sequence

from skeleton.forge.creator.design_graph import (
    EDGE_KINDS,
    DesignGraphEdge,
    DesignGraphError,
    DesignGraphNode,
    DesignGraphSnapshot,
    build_design_graph,
)
from skeleton.forge.creator.generated_history import (
    GeneratedStateHistory,
    StateTransition,
    current_generated_snapshot,
    record_generated_transition,
    undo_generated_state,
)
from skeleton.forge.creator.semantic_diff import (
    SemanticDiff,
    render_semantic_summary,
    semantic_diff,
)
from skeleton.kernel.errors import SkeletonError


MAX_REQUEST_CHARS = 2000
MAX_CLAUSES = 8
MAX_OPS = 8
MAX_TOUCHED = 32
MAX_CHECKS = 16
MAX_SUMMARY_LINES = 32
MAX_DIAGNOSTIC_CHARS = 500
OPS = frozenset({"set", "adjust", "rename", "remove", "connect", "disconnect"})

RepairCheck = Callable[[DesignGraphSnapshot], Iterable[str]]


class NaturalLanguageRepairError(SkeletonError):
    """A repair request is unparseable, ambiguous, unbounded or stale."""

    code = "CRE.NL_REPAIR"
    http_status = 400


def _fail(message: str, *, reason: str, **context: object) -> NoReturn:
    raise NaturalLanguageRepairError(message, context={"reason": reason, **context})


@dataclass(frozen=True, slots=True)
class RepairOp:
    op: str
    node_id: str
    field: str | None = None
    value: object = None
    target_id: str | None = None
    edge_kind: str | None = None
    clause: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "op": self.op, "node_id": self.node_id, "field": self.field,
            "value": self.value, "target_id": self.target_id,
            "edge_kind": self.edge_kind, "clause": self.clause,
        }


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "diagnostics": list(self.diagnostics)}


@dataclass(frozen=True, slots=True)
class RepairProposal:
    request: str
    ops: tuple[RepairOp, ...]
    base_digest: str
    preview: DesignGraphSnapshot
    diff: SemanticDiff
    summary: tuple[str, ...]
    checks: tuple[CheckResult, ...]
    touched_count: int
    digest: str

    @property
    def ok(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "request": self.request,
            "ops": [op.to_dict() for op in self.ops],
            "base_digest": self.base_digest,
            "preview_digest": self.preview.digest,
            "diff_digest": self.diff.digest,
            "summary": list(self.summary),
            "checks": [check.to_dict() for check in self.checks],
            "touched_count": self.touched_count,
            "ok": self.ok,
            "digest": self.digest,
        }


# --------------------------------------------------------------------------- parsing

_SPLIT_RE = re.compile(r"\s*(?:;|\n|\band then\b|\bthen\b|\balso\b)\s*", re.IGNORECASE)
_LEAD_RE = re.compile(r"^(?:please\s+|can you\s+|could you\s+)", re.IGNORECASE)
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("adjust", re.compile(
        r"^(?P<dir>increase|raise|decrease|lower|reduce)\s+(?:the\s+)?(?P<field>[a-z][a-z0-9_]*)"
        r"\s+(?:of|on|for)\s+(?P<node>.+?)\s+by\s+(?P<value>-?\d+(?:\.\d+)?)\s*(?P<pct>%|percent)?$",
        re.IGNORECASE)),
    ("set", re.compile(
        r"^(?:set|change|make)\s+(?:the\s+)?(?P<field>[a-z][a-z0-9_]*)\s+(?:of|on|for)\s+(?P<node>.+?)"
        r"\s+(?:to|=)\s+(?P<value>.+)$", re.IGNORECASE)),
    ("rename", re.compile(r"^rename\s+(?P<node>.+?)\s+(?:to|as)\s+(?P<value>.+)$", re.IGNORECASE)),
    ("remove", re.compile(r"^(?:remove|delete|drop)\s+(?P<node>.+)$", re.IGNORECASE)),
    ("connect", re.compile(
        r"^(?:connect|link)\s+(?P<node>.+?)\s+(?:to|with)\s+(?P<target>.+?)"
        r"(?:\s+as\s+(?P<kind>[a-z_]+))?$", re.IGNORECASE)),
    ("disconnect", re.compile(
        r"^(?:disconnect|unlink)\s+(?P<node>.+?)\s+from\s+(?P<target>.+)$", re.IGNORECASE)),
)


def _clauses(request: str) -> list[str]:
    if not isinstance(request, str) or not request.strip():
        _fail("describe the change you want", reason="empty")
    if len(request) > MAX_REQUEST_CHARS or "\x00" in request:
        _fail("repair request exceeds length/safety bound", reason="bound")
    parts = [_LEAD_RE.sub("", part.strip()).rstrip(".!") for part in _SPLIT_RE.split(request)]
    parts = [part.strip() for part in parts if part and part.strip()]
    if len(parts) > MAX_CLAUSES:
        _fail("too many changes in one request; split it up", reason="bound", maximum=MAX_CLAUSES)
    return parts


def _strip_article(text: str) -> str:
    return re.sub(r"^(?:the|a|an)\s+", "", text.strip().strip("'\""), flags=re.IGNORECASE).strip()


def resolve_node(snapshot: DesignGraphSnapshot, mention: str) -> DesignGraphNode:
    """Resolve an id or a case-insensitive label to exactly one node."""

    text = _strip_article(mention)
    nodes = snapshot.node_map()
    if text in nodes:
        return nodes[text]
    folded = text.casefold()
    matches = [node for node in snapshot.nodes if node.label.casefold() == folded]
    if not matches:
        # "<kind> <label>" such as "mechanic dash"
        head, _, rest = folded.partition(" ")
        matches = [n for n in snapshot.nodes if n.kind == head and n.label.casefold() == rest]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        _fail(f"nothing in the game is called {text!r}", reason="unknown_entity", mention=text)
    _fail(f"{text!r} matches several things; use its id",
          reason="ambiguous_entity", mention=text, candidates=sorted(n.node_id for n in matches))


def _literal(raw: str) -> object:
    text = raw.strip().strip("'\"")
    low = text.casefold()
    if low in ("true", "yes", "on", "enabled"):
        return True
    if low in ("false", "no", "off", "disabled"):
        return False
    if low in ("none", "null", "nothing"):
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def parse_repair_request(snapshot: DesignGraphSnapshot, request: str) -> tuple[RepairOp, ...]:
    """Turn a plain-language request into bounded, fully resolved repair ops."""

    if not isinstance(snapshot, DesignGraphSnapshot):
        _fail("snapshot must be a DesignGraphSnapshot", reason="malformed")
    ops: list[RepairOp] = []
    for clause in _clauses(request):
        for name, pattern in _PATTERNS:
            match = pattern.match(clause)
            if match:
                ops.append(_op_from_match(snapshot, name, match, clause))
                break
        else:
            _fail(f"I can't turn {clause!r} into a change. Try set/increase/decrease/rename/"
                  "remove/connect/disconnect.", reason="unparsed", clause=clause)
    if not ops:
        _fail("describe the change you want", reason="empty")
    if len(ops) > MAX_OPS:
        _fail("repair op count exceeds bound", reason="bound", maximum=MAX_OPS)
    return tuple(ops)


def _op_from_match(snapshot: DesignGraphSnapshot, name: str, m: re.Match[str], clause: str) -> RepairOp:
    node = resolve_node(snapshot, m.group("node"))
    if name in ("set", "adjust"):
        field = m.group("field").lower()
        if field in ("id", "kind"):
            _fail(f"{field} can't be changed by a repair", reason="forbidden_field")
        if field in ("label", "name"):
            if name == "adjust":
                _fail("a name can't be increased or decreased", reason="type_mismatch")
            return RepairOp("rename", node.node_id, value=_strip_article(m.group("value")), clause=clause)
        if name == "set":
            return RepairOp("set", node.node_id, field=field, value=_literal(m.group("value")), clause=clause)
        current = node.attribute_map().get(field)
        if isinstance(current, bool) or not isinstance(current, (int, float)):
            _fail(f"{node.label} has no numeric {field} to adjust", reason="type_mismatch", field=field)
        amount = float(m.group("value"))
        if m.group("pct"):
            amount = abs(current) * amount / 100.0
        if m.group("dir").lower() in ("decrease", "lower", "reduce"):
            amount = -amount
        value: object = current + amount
        if isinstance(current, int) and float(value).is_integer():
            value = int(value)
        if not math.isfinite(float(value)):
            _fail("adjusted value is not finite", reason="bound")
        return RepairOp("adjust", node.node_id, field=field, value=value, clause=clause)
    if name == "rename":
        return RepairOp("rename", node.node_id, value=_strip_article(m.group("value")), clause=clause)
    if name == "remove":
        return RepairOp("remove", node.node_id, clause=clause)
    target = resolve_node(snapshot, m.group("target"))
    if name == "connect":
        kind = (m.group("kind") or "references").lower()
        if kind not in EDGE_KINDS:
            _fail(f"unknown relationship {kind!r}", reason="unknown_edge_kind",
                  allowed=sorted(EDGE_KINDS))
        return RepairOp("connect", node.node_id, target_id=target.node_id, edge_kind=kind, clause=clause)
    return RepairOp("disconnect", node.node_id, target_id=target.node_id, clause=clause)


# --------------------------------------------------------------------------- applying

def apply_repair_ops(
    snapshot: DesignGraphSnapshot, ops: Sequence[RepairOp],
) -> tuple[DesignGraphSnapshot, int]:
    """Apply ops to a copy of the graph. Returns (preview, touched entity count)."""

    if not ops or len(ops) > MAX_OPS:
        _fail("repair op count is outside bounds", reason="bound")
    nodes = {node.node_id: node.to_payload() for node in snapshot.nodes}
    edges = {edge.edge_id: edge.to_payload() for edge in snapshot.edges}
    touched: set[str] = set()
    for op in ops:
        if not isinstance(op, RepairOp) or op.op not in OPS:
            _fail("unsupported repair op", reason="malformed")
        if op.node_id not in nodes:
            _fail(f"{op.node_id} no longer exists", reason="unknown_entity", node_id=op.node_id)
        node = nodes[op.node_id]
        if op.op in ("set", "adjust"):
            node["attributes"] = {**node["attributes"], op.field: op.value}
            touched.add(op.node_id)
        elif op.op == "rename":
            node["label"] = op.value
            touched.add(op.node_id)
        elif op.op == "remove":
            del nodes[op.node_id]
            touched.add(op.node_id)
            for edge_id in [e for e, edge in edges.items()
                            if op.node_id in (edge["source"], edge["target"])]:
                del edges[edge_id]
                touched.add(edge_id)
        elif op.op == "connect":
            if op.target_id not in nodes or op.target_id == op.node_id:
                _fail("can't connect those two things", reason="invalid_edge")
            edge_id = f"edge:repair:{op.edge_kind}:{op.node_id}:{op.target_id}"[:160]
            if edge_id in edges or any(
                e["source"] == op.node_id and e["target"] == op.target_id and e["kind"] == op.edge_kind
                for e in edges.values()
            ):
                _fail("those are already connected that way", reason="no_change")
            edges[edge_id] = {"id": edge_id, "kind": op.edge_kind, "source": op.node_id,
                              "target": op.target_id, "attributes": {}}
            touched.add(edge_id)
        else:
            gone = [e for e, edge in edges.items()
                    if {edge["source"], edge["target"]} == {op.node_id, op.target_id}]
            if not gone:
                _fail("those aren't connected", reason="no_change")
            for edge_id in gone:
                del edges[edge_id]
                touched.add(edge_id)
        if len(touched) > MAX_TOUCHED:
            _fail("repair touches too much of the game; narrow it down",
                  reason="bound", maximum=MAX_TOUCHED)
    try:
        preview = build_design_graph(
            project_id=snapshot.project_id,
            nodes=nodes.values(),
            edges=edges.values(),
            revision=snapshot.revision + 1,
            source_plan_digest=snapshot.source_plan_digest,
        )
    except DesignGraphError as exc:
        _fail(f"repair would break the design graph: {exc}", reason="integrity")
    if _content(preview) == _content(snapshot):
        _fail("that request doesn't change anything", reason="no_change")
    return preview, len(touched)


def _content(snapshot: DesignGraphSnapshot) -> str:
    payload = snapshot.to_payload(include_digest=False)
    payload.pop("revision")
    return json.dumps(payload, sort_keys=True)


# --------------------------------------------------------------------------- proposals

def _run_checks(preview: DesignGraphSnapshot, checks: Sequence[tuple[str, RepairCheck]]) -> tuple[CheckResult, ...]:
    if len(checks) > MAX_CHECKS:
        _fail("too many repair checks", reason="bound", maximum=MAX_CHECKS)
    results = [CheckResult("design_graph_integrity", True, ())]
    for name, check in checks:
        try:
            problems = tuple(str(p)[:MAX_DIAGNOSTIC_CHARS] for p in (check(preview) or ()))[:16]
        except Exception as exc:  # a crashing check is a failed check, never a pass
            problems = (f"check raised {type(exc).__name__}: {exc}"[:MAX_DIAGNOSTIC_CHARS],)
        results.append(CheckResult(str(name), not problems, problems))
    return tuple(results)


def _proposal_digest(request: str, ops: Sequence[RepairOp], base_digest: str, preview_digest: str,
                     diff_digest: str, checks: Sequence[CheckResult]) -> str:
    payload = {
        "schema": "creator.nl_repair_proposal.v1", "request": request,
        "ops": [op.to_dict() for op in ops], "base_digest": base_digest,
        "preview_digest": preview_digest, "diff_digest": diff_digest,
        "checks": [c.to_dict() for c in checks],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def propose_repair(
    history: GeneratedStateHistory,
    request: str,
    *,
    checks: Sequence[tuple[str, RepairCheck]] = (),
) -> RepairProposal:
    """Parse, apply to a preview, diff and test. Never changes the history."""

    current = current_generated_snapshot(history)
    ops = parse_repair_request(current, request)
    preview, touched = apply_repair_ops(current, ops)
    diff = semantic_diff(current, preview)
    summary = render_semantic_summary(diff, limit=MAX_SUMMARY_LINES)
    results = _run_checks(preview, checks)
    digest = _proposal_digest(request, ops, current.digest, preview.digest, diff.digest, results)
    return RepairProposal(request, ops, current.digest, preview, diff, summary, results, touched, digest)


def accept_repair(
    history: GeneratedStateHistory,
    proposal: RepairProposal,
    *,
    checks: Sequence[tuple[str, RepairCheck]] = (),
) -> tuple[GeneratedStateHistory, DesignGraphSnapshot, StateTransition]:
    """Record an approved proposal as one undoable transition.

    The proposal is recomputed from the current history and the same checks;
    a stale, forged or failing proposal is refused.
    """

    if not isinstance(proposal, RepairProposal):
        _fail("proposal must be a RepairProposal", reason="malformed")
    current = current_generated_snapshot(history)
    if current.digest != proposal.base_digest:
        _fail("the game changed since this repair was previewed; preview it again", reason="stale")
    fresh = propose_repair(history, proposal.request, checks=checks)
    if fresh.digest != proposal.digest:
        _fail("repair proposal does not match its recomputed evidence", reason="digest_mismatch")
    if not fresh.ok:
        failing = [c.name for c in fresh.checks if not c.passed]
        _fail("repair checks failed; nothing was applied", reason="checks_failed", failing=failing)
    label = f"repair: {' '.join(proposal.request.split())}"[:120].strip()
    next_history, transition = record_generated_transition(history, current, fresh.preview, label=label)
    return next_history, fresh.preview, transition


def rollback_repair(
    history: GeneratedStateHistory,
) -> tuple[GeneratedStateHistory, DesignGraphSnapshot, StateTransition]:
    """Undo the latest accepted repair exactly (B018 content-addressed undo)."""

    current = current_generated_snapshot(history)
    next_history, restored, transition = undo_generated_state(history, current)
    if not transition.label.startswith("repair: "):
        _fail("the latest change is not a repair", reason="not_a_repair")
    return next_history, restored, transition


__all__ = [
    "MAX_OPS", "MAX_TOUCHED", "CheckResult", "NaturalLanguageRepairError", "RepairCheck",
    "RepairOp", "RepairProposal", "accept_repair", "apply_repair_ops",
    "parse_repair_request", "propose_repair", "resolve_node", "rollback_repair",
]
