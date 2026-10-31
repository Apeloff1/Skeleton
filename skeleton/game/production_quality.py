"""Deterministic candidate-quality gates for the canonical game production plane.

These are candidate audits, not production certification. All inputs are explicit,
untrusted, and bounded; approval cannot be inferred from missing evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import PurePosixPath
from typing import Mapping, Sequence


class QualityGateError(ValueError):
    """Invalid or unsafe production evidence."""


@dataclass(frozen=True)
class Finding:
    gate: str
    code: str
    subject: str

    def as_dict(self) -> dict[str, str]:
        return {"gate": self.gate, "code": self.code, "subject": self.subject}


@dataclass(frozen=True)
class GateResult:
    name: str
    findings: tuple[Finding, ...]
    evidence_digest: str

    @property
    def passed(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed,
                "findings": [f.as_dict() for f in self.findings],
                "evidence_digest": self.evidence_digest}


def _digest(value: object) -> str:
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, OverflowError) as exc:
        raise QualityGateError("evidence must be canonical JSON") from exc
    if len(data) > 8_000_000:
        raise QualityGateError("evidence exceeds size budget")
    return sha256(data).hexdigest()


def _items(value: object, label: str, limit: int = 10000) -> list:
    if not isinstance(value, (tuple, list)) or len(value) > limit:
        raise QualityGateError(f"{label} must be a bounded sequence")
    return list(value)


def _record(value: object, label: str) -> Mapping:
    if not isinstance(value, dict):
        raise QualityGateError(f"{label} must be an object")
    return value


def _result(name: str, findings: list[Finding], evidence: object) -> GateResult:
    return GateResult(name, tuple(sorted(findings, key=lambda f: (f.code, f.subject))),
                      _digest(evidence))


def audit_world_graph(graph: Mapping[str, object]) -> GateResult:
    """Check playable adjacency, destinations, duplicate nodes and victory reachability."""
    graph = _record(graph, "world")
    nodes = _items(graph.get("nodes"), "nodes")
    edges = _items(graph.get("edges"), "edges", 50000)
    findings: list[Finding] = []
    ids: set[str] = set()
    for node in nodes:
        node = _record(node, "node")
        ident = node.get("id")
        if not isinstance(ident, str) or not ident or len(ident) > 256:
            raise QualityGateError("node ids must be bounded nonempty strings")
        if ident in ids:
            findings.append(Finding("world", "duplicate_node", ident))
        ids.add(ident)
    start, victory = graph.get("start"), graph.get("victory")
    adjacency: dict[str, set[str]] = {i: set() for i in ids}
    for edge in edges:
        edge = _record(edge, "edge")
        a, b = edge.get("from"), edge.get("to")
        if not isinstance(a, str) or not isinstance(b, str):
            raise QualityGateError("edge endpoints must be strings")
        if a not in ids or b not in ids:
            findings.append(Finding("world", "orphan_edge", f"{a}->{b}"))
        else:
            adjacency[a].add(b)
    if start not in ids:
        findings.append(Finding("world", "missing_start", str(start)))
    if victory not in ids:
        findings.append(Finding("world", "missing_victory", str(victory)))
    seen: set[str] = set()
    frontier = [start] if start in ids else []
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(adjacency[current] - seen)
    if victory not in seen:
        findings.append(Finding("world", "unreachable_victory", str(victory)))
    for ident in sorted(ids - seen):
        findings.append(Finding("world", "unreachable_node", ident))
    return _result("world", findings, graph)


def audit_story_canon(story: Mapping[str, object]) -> GateResult:
    """Check authored scene prerequisites and character/source continuity."""
    story = _record(story, "story")
    scenes = _items(story.get("scenes"), "scenes")
    cast = _items(story.get("cast"), "cast")
    findings: list[Finding] = []
    cast_ids: set[str] = set()
    for c in cast:
        c = _record(c, "character")
        ident = c.get("id")
        if not isinstance(ident, str) or not ident:
            raise QualityGateError("character id required")
        if ident in cast_ids:
            findings.append(Finding("canon", "duplicate_character", ident))
        cast_ids.add(ident)
    seen: set[str] = set()
    all_ids: list[str] = []
    for s in scenes:
        s = _record(s, "scene")
        ident = s.get("id")
        if not isinstance(ident, str) or not ident:
            raise QualityGateError("scene id required")
        all_ids.append(ident)
        if ident in seen:
            findings.append(Finding("canon", "duplicate_scene", ident))
        for pre in _items(s.get("prerequisites", []), "prerequisites", 256):
            if not isinstance(pre, str):
                raise QualityGateError("prerequisites must be string scene ids")
            if pre not in seen:
                findings.append(Finding("canon", "unmet_prerequisite", f"{ident}:{pre}"))
        for actor in _items(s.get("speakers", []), "speakers", 128):
            if not isinstance(actor, str):
                raise QualityGateError("speaker must be a string")
            if actor not in cast_ids:
                findings.append(Finding("canon", "unknown_speaker", f"{ident}:{actor}"))
        seen.add(ident)
    if not all_ids:
        findings.append(Finding("canon", "empty_story", "scenes"))
    return _result("canon", findings, story)


def audit_asset_integrity(assets: Sequence[dict]) -> GateResult:
    """Check rooted relative paths, collisions and SHA-256 declarations."""
    assets = _items(assets, "assets")
    findings: list[Finding] = []
    seen: set[str] = set()
    for item in assets:
        item = _record(item, "asset")
        path = item.get("path")
        digest = item.get("sha256")
        if not isinstance(path, str) or not path or len(path) > 1024:
            raise QualityGateError("asset path must be bounded string")
        p = PurePosixPath(path)
        if (p.is_absolute() or "\\" in path or
            any(part in (".", "..") for part in path.split("/")) or
            path.startswith("/") or not p.parts):
            findings.append(Finding("assets", "unsafe_path", path))
        if path in seen:
            findings.append(Finding("assets", "duplicate_path", path))
        seen.add(path)
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            findings.append(Finding("assets", "invalid_digest", path))
        if not isinstance(item.get("bytes"), int) or isinstance(item.get("bytes"), bool) or item["bytes"] < 0:
            findings.append(Finding("assets", "invalid_size", path))
    if not assets:
        findings.append(Finding("assets", "empty_manifest", "assets"))
    return _result("assets", findings, assets)


def audit_build_replay(builds: Sequence[dict]) -> GateResult:
    """Verify multiple separately recorded build outputs have identical sources and artifact hashes."""
    builds = _items(builds, "builds", 64)
    findings: list[Finding] = []
    if len(builds) < 2:
        findings.append(Finding("replay", "insufficient_runs", "builds"))
    baseline = None
    for i, run in enumerate(builds):
        run = _record(run, "build")
        source = run.get("source_sha256")
        files = _record(run.get("files"), "build.files")
        if not isinstance(source, str) or len(source) != 64 or any(c not in "0123456789abcdef" for c in source):
            findings.append(Finding("replay", "invalid_source", str(i)))
        if not files or not all(isinstance(k, str) and isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v) for k, v in files.items()):
            findings.append(Finding("replay", "invalid_file_digest", str(i)))
        signature = (source, _digest(files))
        if baseline is not None and signature != baseline:
            findings.append(Finding("replay", "build_divergence", str(i)))
        if baseline is None:
            baseline = signature
    return _result("replay", findings, builds)


def audit_frame_budget(frames: Sequence[dict], *, max_ms: float = 16.67,
                       max_draw_calls: int = 1200) -> GateResult:
    """Gate frame tails and geometric pressure with explicit, non-fabricated samples."""
    frames = _items(frames, "frames", 100000)
    if not math.isfinite(max_ms) or max_ms <= 0 or not isinstance(max_draw_calls, int) or max_draw_calls <= 0:
        raise QualityGateError("invalid frame budgets")
    findings: list[Finding] = []
    timings: list[float] = []
    for i, frame in enumerate(frames):
        frame = _record(frame, "frame")
        ms, draws = frame.get("ms"), frame.get("draw_calls")
        if isinstance(ms, bool) or not isinstance(ms, (int, float)) or not math.isfinite(ms) or ms < 0:
            raise QualityGateError("frame time must be finite and nonnegative")
        if isinstance(draws, bool) or not isinstance(draws, int) or draws < 0:
            raise QualityGateError("draw calls must be nonnegative integer")
        timings.append(float(ms))
        if draws > max_draw_calls:
            findings.append(Finding("performance", "draw_budget", str(i)))
    if not timings:
        findings.append(Finding("performance", "no_measurements", "frames"))
    else:
        ordered = sorted(timings)
        for percentile in (95, 99):
            index = math.ceil(percentile / 100 * len(ordered)) - 1
            if ordered[index] > max_ms:
                findings.append(Finding("performance", f"p{percentile}_frame_budget", str(ordered[index])))
    return _result("performance", findings, {"frames": frames, "max_ms": max_ms,
                                              "max_draw_calls": max_draw_calls})


def audit_rights_provenance(sources: Sequence[dict]) -> GateResult:
    """Require explicit reviewed source rights; never infer legal clearance."""
    sources = _items(sources, "sources")
    findings: list[Finding] = []
    if not sources:
        findings.append(Finding("rights", "missing_sources", "sources"))
    seen: set[str] = set()
    for source in sources:
        source = _record(source, "source")
        ident = source.get("id")
        if not isinstance(ident, str) or not ident:
            raise QualityGateError("source id required")
        if ident in seen:
            findings.append(Finding("rights", "duplicate_source", ident))
        seen.add(ident)
        if source.get("origin") not in ("original", "licensed", "public_domain"):
            findings.append(Finding("rights", "unresolved_origin", ident))
        if source.get("reviewed") is not True:
            findings.append(Finding("rights", "unreviewed", ident))
        if not isinstance(source.get("evidence_ref"), str) or not source["evidence_ref"].strip():
            findings.append(Finding("rights", "missing_evidence", ident))
    return _result("rights", findings, sources)


def audit_release_candidate(bundle: Mapping[str, object]) -> dict[str, object]:
    """Compose six independent gates plus the fail-closed release decision gate.

    This result is a candidate readiness signal only; rights evidence is asserted,
    not independently authenticated, and native device/runtime signoff is separate.
    """
    bundle = _record(bundle, "candidate")
    results = (
        audit_world_graph(bundle.get("world")),
        audit_story_canon(bundle.get("story")),
        audit_asset_integrity(bundle.get("assets")),
        audit_build_replay(bundle.get("builds")),
        audit_frame_budget(bundle.get("frames")),
        audit_rights_provenance(bundle.get("sources")),
    )
    findings = [f.as_dict() for r in results for f in r.findings]
    return {"schema": "game.candidate.quality.v1", "candidate_passed": not findings,
            "release_certified": False, "gates": [r.as_dict() for r in results],
            "findings": findings, "evidence_digest": _digest([r.as_dict() for r in results])}
