"""GF-G chunk-level edit receipts, telemetry source adapters and reconciliation.

TODO.md Game Frontier P0 items (tracked in #4167):
- GF-P0-149: per-chunk shader/light/shadow/terrain/weather source-reference and
  vertex-diff receipts on game world edits (``build_edit_receipts``).
- GF-P0-166: telemetry source adapters for collision normals/forces, lighting,
  audio and streamed mesh LOD per chunk (``TelemetryAdapter``/``ingest_telemetry``).
- GF-P0-164: reconcile rendered/GPU/physics output, native capture, journal
  source and per-chunk evidence (``reconcile_chunk_evidence``).

Extend-only companion to ``game_frontier_chunk_evidence``: same seal shape
(sha256 over canonical JSON), no second evidence store. Fail closed: anything
not recomputable from its sources is rejected. Telemetry is only marked
``authoritative`` when it comes from a declared native adapter; otherwise it is
a ``candidate``. Target-hardware reconciliation cannot be proven in CI, so a
match without a hardware attestation is ``matched_unattested``, never ``verified``.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_EDIT = "game_frontier.chunk_edit_receipt.v1"
SCHEMA_TELEMETRY = "game_frontier.chunk_telemetry.v1"
SCHEMA_RECONCILE = "game_frontier.chunk_reconcile.v1"

SOURCE_KINDS = ("shader", "light", "shadow", "terrain", "weather")
TELEMETRY_CHANNELS = ("collision", "lighting", "audio", "mesh_lod")


class ChunkTelemetryError(ValueError):
    pass


def _hash(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _sealed(body: dict) -> dict:
    return {**body, "digest": _hash(body)}


def _check_seal(doc: Mapping[str, Any]) -> bool:
    body = {k: v for k, v in doc.items() if k != "digest"}
    try:
        return doc.get("digest") == _hash(body)
    except (TypeError, ValueError):
        return False


def _finite(values: Iterable[Any], name: str) -> list[float]:
    out = []
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ChunkTelemetryError(f"{name} must be finite numbers")
        out.append(float(v))
    return out


def _chunk_id(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ChunkTelemetryError("chunk id must be a non-empty string")
    return value


# --- GF-P0-149 --------------------------------------------------------------

def _vertex_diff(before: Sequence[Sequence[float]], after: Sequence[Sequence[float]]) -> dict[str, Any]:
    b = [tuple(_finite(v, "vertex")) for v in before]
    a = [tuple(_finite(v, "vertex")) for v in after]
    if any(len(v) != 3 for v in (*b, *a)):
        raise ChunkTelemetryError("vertices must be 3D")
    moved = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
    max_disp = max((math.dist(a[i], b[i]) for i in moved), default=0.0)
    return {
        "before_digest": _hash([list(v) for v in b]),
        "after_digest": _hash([list(v) for v in a]),
        "moved": moved,
        "added": max(0, len(a) - len(b)),
        "removed": max(0, len(b) - len(a)),
        "max_displacement": round(max_disp, 9),
    }


def build_edit_receipts(edit: Mapping[str, Any]) -> dict[str, Any]:
    """Seal one world edit into per-chunk receipts.

    ``edit`` = {"edit_id", "chunks": {chunk_id: {"sources": {kind: [{"id","content"}]},
    "vertices_before": [...], "vertices_after": [...]}}}.
    Every referenced source is pinned by content digest; unknown kinds are rejected.
    """
    edit_id = edit.get("edit_id")
    if not isinstance(edit_id, str) or not edit_id:
        raise ChunkTelemetryError("edit_id required")
    chunks = edit.get("chunks")
    if not isinstance(chunks, Mapping) or not chunks:
        raise ChunkTelemetryError("edit must touch at least one chunk")
    receipts = []
    for cid in sorted(chunks):
        entry = chunks[cid]
        sources = entry.get("sources", {})
        unknown = set(sources) - set(SOURCE_KINDS)
        if unknown:
            raise ChunkTelemetryError(f"{cid}: unknown source kinds {sorted(unknown)}")
        refs = {}
        for kind in SOURCE_KINDS:
            items = []
            for ref in sources.get(kind, ()):
                if not isinstance(ref.get("id"), str) or "content" not in ref:
                    raise ChunkTelemetryError(f"{cid}: {kind} source needs id and content")
                items.append({"id": ref["id"], "content_digest": _hash(ref["content"])})
            refs[kind] = sorted(items, key=lambda r: r["id"])
        diff = _vertex_diff(entry.get("vertices_before", ()), entry.get("vertices_after", ()))
        if not any(refs.values()) and not (diff["moved"] or diff["added"] or diff["removed"]):
            raise ChunkTelemetryError(f"{cid}: edit receipt has no source reference or vertex change")
        receipts.append(_sealed({"chunk_id": _chunk_id(cid), "sources": refs, "vertex_diff": diff}))
    return _sealed({"schema": SCHEMA_EDIT, "edit_id": edit_id, "receipts": receipts})


def verify_edit_receipts(doc: Mapping[str, Any], edit: Mapping[str, Any]) -> bool:
    """Independent verifier: recompute from the source edit; stored hashes alone are not trusted."""
    try:
        return _check_seal(doc) and build_edit_receipts(edit) == dict(doc)
    except (ChunkTelemetryError, TypeError, AttributeError):
        return False


# --- GF-P0-166 --------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TelemetryAdapter:
    """Declares a telemetry source. ``native`` must be True for authoritative data."""

    adapter_id: str
    engine: str
    native: bool
    channels: tuple[str, ...] = TELEMETRY_CHANNELS

    def __post_init__(self) -> None:
        if not self.adapter_id or not self.engine:
            raise ChunkTelemetryError("adapter_id and engine required")
        bad = set(self.channels) - set(TELEMETRY_CHANNELS)
        if bad:
            raise ChunkTelemetryError(f"unknown telemetry channels {sorted(bad)}")


def _normalize_sample(channel: str, sample: Mapping[str, Any]) -> dict[str, Any]:
    if channel == "collision":
        normal = _finite(sample.get("normal", ()), "collision.normal")
        force = _finite(sample.get("force", ()), "collision.force")
        if len(normal) != 3 or len(force) != 3:
            raise ChunkTelemetryError("collision normal/force must be 3D")
        length = math.sqrt(sum(c * c for c in normal))
        if abs(length - 1.0) > 1e-3:
            raise ChunkTelemetryError("collision normal must be unit length")
        return {"normal": normal, "force": force}
    if channel == "lighting":
        lux = _finite([sample.get("luminance")], "lighting.luminance")[0]
        if lux < 0:
            raise ChunkTelemetryError("luminance must be non-negative")
        return {"luminance": lux, "light_ids": sorted(map(str, sample.get("light_ids", ())))}
    if channel == "audio":
        rms = _finite([sample.get("rms_db")], "audio.rms_db")[0]
        return {"rms_db": rms, "bus": str(sample.get("bus", "master"))}
    if channel == "mesh_lod":
        lod = sample.get("lod")
        tris = sample.get("triangles")
        if isinstance(lod, bool) or not isinstance(lod, int) or lod < 0:
            raise ChunkTelemetryError("mesh_lod.lod must be a non-negative int")
        if isinstance(tris, bool) or not isinstance(tris, int) or tris < 0:
            raise ChunkTelemetryError("mesh_lod.triangles must be a non-negative int")
        return {"lod": lod, "triangles": tris}
    raise ChunkTelemetryError(f"unknown channel {channel}")


def ingest_telemetry(adapter: TelemetryAdapter, frame: int, samples: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Normalize one frame of per-chunk telemetry: samples[chunk_id][channel] -> sample."""
    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise ChunkTelemetryError("frame must be a non-negative int")
    chunks = []
    for cid in sorted(samples):
        per = samples[cid]
        bad = set(per) - set(adapter.channels)
        if bad:
            raise ChunkTelemetryError(f"{cid}: adapter does not declare channels {sorted(bad)}")
        chunks.append({"chunk_id": _chunk_id(cid),
                       "channels": {ch: _normalize_sample(ch, per[ch]) for ch in sorted(per)}})
    return _sealed({
        "schema": SCHEMA_TELEMETRY,
        "adapter": {"id": adapter.adapter_id, "engine": adapter.engine, "native": adapter.native},
        "authority": "authoritative" if adapter.native else "candidate",
        "frame": frame,
        "chunks": chunks,
    })


# --- GF-P0-164 --------------------------------------------------------------

def reconcile_chunk_evidence(
    *,
    rendered: Mapping[str, str],
    capture: Mapping[str, Any],
    journal: Mapping[str, str],
    evidence: Mapping[str, str],
) -> dict[str, Any]:
    """Reconcile per-chunk digests from four planes.

    ``rendered``/``journal``/``evidence``: chunk_id -> digest. ``capture``:
    {"chunks": {chunk_id: digest}, "hardware": optional attestation mapping}.
    A chunk is ``matched`` only when all four planes agree; missing planes are
    ``missing``; disagreements are ``mismatch``. Overall status is ``verified``
    only with a hardware attestation (and it is sealed); without one, an all-match
    result is ``matched_unattested`` (fail closed: no target-hardware claim).
    """
    cap_chunks = capture.get("chunks", {})
    hardware = capture.get("hardware")
    planes = {"rendered": rendered, "capture": cap_chunks, "journal": journal, "evidence": evidence}
    ids = sorted(set().union(*[set(p) for p in planes.values()]))
    rows = []
    for cid in ids:
        digests = {name: plane.get(cid) for name, plane in planes.items()}
        missing = sorted(n for n, d in digests.items() if not d)
        if missing:
            state = "missing"
        elif len(set(digests.values())) == 1:
            state = "matched"
        else:
            state = "mismatch"
        rows.append({"chunk_id": cid, "state": state, "missing": missing, "digests": digests})
    all_match = bool(rows) and all(r["state"] == "matched" for r in rows)
    attested = isinstance(hardware, Mapping) and bool(hardware.get("device")) and bool(hardware.get("driver"))
    if not all_match:
        status = "failed"
    elif attested:
        status = "verified"
    else:
        status = "matched_unattested"
    return _sealed({
        "schema": SCHEMA_RECONCILE,
        "status": status,
        "hardware": dict(hardware) if attested else None,
        "chunks": rows,
    })


def verify_sealed(doc: Mapping[str, Any]) -> bool:
    return isinstance(doc, Mapping) and _check_seal(doc)


__all__ = [
    "SCHEMA_EDIT", "SCHEMA_RECONCILE", "SCHEMA_TELEMETRY", "SOURCE_KINDS", "TELEMETRY_CHANNELS",
    "ChunkTelemetryError", "TelemetryAdapter", "build_edit_receipts", "ingest_telemetry",
    "reconcile_chunk_evidence", "verify_edit_receipts", "verify_sealed",
]
