"""B038 — AI generation provenance.

Success criterion (game_creation_batches.json): "Every AI-produced artifact
records model, inputs, parameters, sources, transformations and evals."

Two layers:

* :class:`ProvenanceRecord` — the per-step seam consumed by B039
  (``skeleton.gameforge.batch_b039``). Field names, order and types match B039's
  typed placeholder exactly, so B039 can import it from here unchanged.
* :class:`GenerationProvenance` + :class:`ProvenanceLedger` — the full record for
  any AI-produced artifact (model, inputs, parameters, sources,
  transformations, evals), content-addressed and hash-chained so tampering or
  reordering is detectable.

Depends on B031 (model routing) only through plain ``model``/``provider``
strings; nothing here calls a model.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

SCHEMA = "gameforge.b038.generation_provenance.v1"
GENESIS = "0" * 64
MAX_ITEMS = 256
MAX_TEXT = 512


class ProvenanceError(ValueError):
    """A provenance record is malformed or a ledger fails verification."""


def digest(obj: object) -> str:
    """Short content digest; identical to B039's ``digest`` (16 hex chars)."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("ascii")


def _text(name: str, value: object, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not value and not allow_empty) or len(value) > MAX_TEXT or "\x00" in value:
        raise ProvenanceError(f"{name} must be a non-empty string of at most {MAX_TEXT} chars")
    return value


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProvenanceError(f"{name} must be a finite number")
    return float(value)


# -- B039 seam ---------------------------------------------------------------
@dataclass(frozen=True)
class ProvenanceRecord:
    """B038 seam: provenance of one repair step (interface fixed by B039)."""
    step: int
    model: str
    provider: str
    input_digest: str
    output_digest: str
    diagnoses: tuple[str, ...]
    score_before: float
    score_after: float
    cost: float

    def validate(self) -> ProvenanceRecord:
        if isinstance(self.step, bool) or not isinstance(self.step, int) or self.step < 1:
            raise ProvenanceError("step must be a positive int")
        _text("model", self.model)
        _text("provider", self.provider)
        _text("input_digest", self.input_digest)
        _text("output_digest", self.output_digest)
        if not isinstance(self.diagnoses, tuple) or not all(isinstance(d, str) for d in self.diagnoses):
            raise ProvenanceError("diagnoses must be a tuple of str")
        _finite("score_before", self.score_before)
        _finite("score_after", self.score_after)
        if _finite("cost", self.cost) < 0:
            raise ProvenanceError("cost must be non-negative")
        return self

    def to_record(self) -> dict[str, Any]:
        return {"step": self.step, "model": self.model, "provider": self.provider,
                "input_digest": self.input_digest, "output_digest": self.output_digest,
                "diagnoses": list(self.diagnoses), "score_before": self.score_before,
                "score_after": self.score_after, "cost": self.cost}


# -- full generation provenance ---------------------------------------------
@dataclass(frozen=True)
class SourceRef:
    """A grounding source used for generation (document, asset, URL, prior artifact)."""
    kind: str
    ref: str
    content_digest: str = ""

    def to_record(self) -> dict[str, Any]:
        return {"kind": self.kind, "ref": self.ref, "content_digest": self.content_digest}


@dataclass(frozen=True)
class Transformation:
    """A post-generation step (sanitize, format, repair, compress...)."""
    name: str
    input_digest: str
    output_digest: str
    detail: str = ""

    def to_record(self) -> dict[str, Any]:
        return {"name": self.name, "input_digest": self.input_digest,
                "output_digest": self.output_digest, "detail": self.detail}


@dataclass(frozen=True)
class EvalRecord:
    name: str
    score: float
    passed: bool
    detail: str = ""

    def to_record(self) -> dict[str, Any]:
        return {"name": self.name, "score": self.score, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class GenerationProvenance:
    """Complete provenance for one AI-produced artifact."""
    artifact_id: str
    artifact_digest: str
    model: str
    provider: str
    input_digest: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    sources: tuple[SourceRef, ...] = ()
    transformations: tuple[Transformation, ...] = ()
    evals: tuple[EvalRecord, ...] = ()
    steps: tuple[ProvenanceRecord, ...] = ()

    def __post_init__(self) -> None:
        for name in ("artifact_id", "artifact_digest", "model", "provider", "input_digest"):
            _text(name, getattr(self, name))
        if not isinstance(self.parameters, Mapping) or not all(isinstance(k, str) for k in self.parameters):
            raise ProvenanceError("parameters must be a str-keyed mapping")
        for name in ("sources", "transformations", "evals", "steps"):
            items = getattr(self, name)
            if not isinstance(items, tuple) or len(items) > MAX_ITEMS:
                raise ProvenanceError(f"{name} must be a tuple of at most {MAX_ITEMS} items")
        for s in self.sources:
            _text("source.kind", s.kind)
            _text("source.ref", s.ref)
        for t in self.transformations:
            _text("transformation.name", t.name)
        for e in self.evals:
            _text("eval.name", e.name)
            _finite("eval.score", e.score)
        for i, st in enumerate(self.steps, 1):
            st.validate()
            if st.step != i:
                raise ProvenanceError("steps must be numbered 1..n in order")
        try:
            json.dumps(dict(self.parameters), sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ProvenanceError("parameters must be JSON-serialisable") from exc
        # The transformation chain must end at the recorded artifact.
        if self.transformations and self.transformations[-1].output_digest != self.artifact_digest:
            raise ProvenanceError("last transformation must produce the artifact digest")

    @property
    def evals_passed(self) -> bool:
        return bool(self.evals) and all(e.passed for e in self.evals)

    def to_record(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA, "artifact_id": self.artifact_id, "artifact_digest": self.artifact_digest,
            "model": self.model, "provider": self.provider, "input_digest": self.input_digest,
            "parameters": json.loads(_canonical(dict(self.parameters))),
            "sources": [s.to_record() for s in self.sources],
            "transformations": [t.to_record() for t in self.transformations],
            "evals": [e.to_record() for e in self.evals],
            "steps": [s.to_record() for s in self.steps],
        }

    @property
    def content_id(self) -> str:
        return hashlib.sha256(_canonical(self.to_record())).hexdigest()


def from_repair_steps(artifact_id: str, artifact: object, original_input: object,
                      steps: Sequence[ProvenanceRecord], *, parameters: Mapping[str, Any] | None = None,
                      evals: Iterable[EvalRecord] = ()) -> GenerationProvenance:
    """Lift a B039 repair trace (``RepairOutcome.provenance``) into full provenance."""
    if not steps:
        raise ProvenanceError("repair trace is empty")
    last = steps[-1]
    transforms = tuple(Transformation(f"repair_step_{s.step}", s.input_digest, s.output_digest,
                                      ",".join(s.diagnoses)) for s in steps)
    art = digest(artifact)
    # Rejected steps do not change the artifact; the final artifact is whichever output was kept.
    kept = [t for t in transforms if t.output_digest == art]
    if kept:
        transforms = transforms[: transforms.index(kept[-1]) + 1]
    else:
        transforms = transforms + (Transformation("final", transforms[-1].output_digest, art, "artifact as returned"),)
    return GenerationProvenance(artifact_id, art, last.model, last.provider, digest(original_input),
                                dict(parameters or {}), (), transforms, tuple(evals), tuple(steps))


class ProvenanceLedger:
    """Append-only, hash-chained ledger of :class:`GenerationProvenance` entries."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._head = GENESIS

    @property
    def head(self) -> str:
        return self._head

    def append(self, prov: GenerationProvenance) -> str:
        if not isinstance(prov, GenerationProvenance):
            raise ProvenanceError("ledger accepts GenerationProvenance only")
        body = {"seq": len(self._entries), "prev": self._head, "content_id": prov.content_id,
                "record": prov.to_record()}
        h = hashlib.sha256(_canonical(body)).hexdigest()
        self._entries.append({**body, "hash": h})
        self._head = h
        return h

    def entries(self) -> list[dict[str, Any]]:
        return [json.loads(_canonical(e)) for e in self._entries]

    def lookup(self, artifact_digest: str) -> list[dict[str, Any]]:
        return [e for e in self.entries() if e["record"]["artifact_digest"] == artifact_digest]

    @staticmethod
    def verify(entries: Sequence[Mapping[str, Any]]) -> bool:
        prev = GENESIS
        for i, e in enumerate(entries):
            body = {k: e[k] for k in ("seq", "prev", "content_id", "record") if k in e}
            if (e.get("seq") != i or e.get("prev") != prev
                    or hashlib.sha256(_canonical(body)).hexdigest() != e.get("hash")
                    or hashlib.sha256(_canonical(e.get("record"))).hexdigest() != e.get("content_id")):
                raise ProvenanceError(f"ledger broken at seq {i}")
            prev = e["hash"]
        return True
