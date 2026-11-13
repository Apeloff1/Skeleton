"""Tests for #807 B038 (AI generation provenance) and its B039 seam."""
from __future__ import annotations

import dataclasses
import importlib
import typing

import pytest

from skeleton.gameforge.batch_b038 import (
    EvalRecord, GenerationProvenance, ProvenanceError, ProvenanceLedger, ProvenanceRecord,
    SourceRef, Transformation, digest, from_repair_steps,
)

B039_FIELDS = [
    ("step", int), ("model", str), ("provider", str), ("input_digest", str),
    ("output_digest", str), ("diagnoses", tuple[str, ...]), ("score_before", float),
    ("score_after", float), ("cost", float),
]


def rec(step=1, **kw):
    base = dict(step=step, model="m", provider="p", input_digest="a" * 16, output_digest="b" * 16,
                diagnoses=("schema",), score_before=0.1, score_after=0.5, cost=1.0)
    base.update(kw)
    return ProvenanceRecord(**base)


def gen(**kw):
    base = dict(artifact_id="quest-1", artifact_digest=digest({"q": 1}), model="m", provider="p",
                input_digest=digest({"prompt": "x"}), parameters={"temperature": 0.2, "seed": 7},
                sources=(SourceRef("doc", "lore.md", "c" * 16),),
                transformations=(Transformation("sanitize", "d" * 16, digest({"q": 1})),),
                evals=(EvalRecord("reachability", 1.0, True),))
    base.update(kw)
    return GenerationProvenance(**base)


# -- B039 interface parity ---------------------------------------------------
def test_record_matches_b039_placeholder_exactly():
    hints = typing.get_type_hints(ProvenanceRecord)
    fields = dataclasses.fields(ProvenanceRecord)
    assert [(f.name, hints[f.name]) for f in fields] == B039_FIELDS
    assert ProvenanceRecord.__dataclass_params__.frozen
    assert all(f.default is dataclasses.MISSING for f in fields)


def test_positional_construction_like_b039():
    r = ProvenanceRecord(1, "m", "p", "i", "o", ("logic",), 0.0, 1.0, 2.5)
    assert r.step == 1 and r.diagnoses == ("logic",) and r.cost == 2.5
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.step = 2  # type: ignore[misc]


def test_digest_matches_b039_formula():
    import hashlib
    import json
    obj = {"b": 2, "a": [1, 2]}
    assert digest(obj) == hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def test_parity_with_b039_module_if_present():
    try:
        b039 = importlib.import_module("skeleton.gameforge.batch_b039.self_repair")
    except ImportError:
        pytest.skip("B039 not on this branch")
    theirs = typing.get_type_hints(b039.ProvenanceRecord)
    assert [(f.name, theirs[f.name]) for f in dataclasses.fields(b039.ProvenanceRecord)] == B039_FIELDS


# -- validation ----------------------------------------------------------------
@pytest.mark.parametrize("bad", [dict(step=0), dict(step=True), dict(model=""), dict(cost=-1.0),
                                 dict(score_after=float("nan")), dict(diagnoses=["x"])])
def test_record_validate_rejects(bad):
    with pytest.raises(ProvenanceError):
        rec(**bad).validate()


def test_generation_records_all_required_facets():
    r = gen().to_record()
    for key in ("model", "provider", "input_digest", "parameters", "sources", "transformations", "evals"):
        assert key in r
    assert gen().evals_passed


@pytest.mark.parametrize("bad", [dict(model=""), dict(parameters={1: 2}), dict(parameters={"f": object()}),
                                 dict(sources=[SourceRef("d", "r")]),
                                 dict(transformations=(Transformation("t", "a", "wrong"),)),
                                 dict(evals=(EvalRecord("e", float("inf"), True),)),
                                 dict(steps=(rec(step=2),))])
def test_generation_rejects(bad):
    with pytest.raises(ProvenanceError):
        gen(**bad)


def test_content_id_deterministic_and_sensitive():
    assert gen().content_id == gen().content_id
    assert gen().content_id != gen(parameters={"temperature": 0.3, "seed": 7}).content_id


def test_no_evals_is_not_passed():
    assert not gen(evals=()).evals_passed


# -- repair trace lifting --------------------------------------------------------
def test_from_repair_steps_truncates_to_kept_output():
    a0, a1, a2 = {"hp": 0}, {"hp": 5}, {"hp": 9}
    steps = [rec(1, input_digest=digest(a0), output_digest=digest(a1)),
             rec(2, input_digest=digest(a1), output_digest=digest(a2))]
    p = from_repair_steps("npc", a1, a0, steps, parameters={"budget": 3})
    assert p.artifact_digest == digest(a1) and len(p.transformations) == 1 and len(p.steps) == 2


def test_from_repair_steps_appends_final_when_unmatched():
    steps = [rec(1)]
    p = from_repair_steps("npc", {"z": 1}, {"z": 0}, steps)
    assert p.transformations[-1].output_digest == digest({"z": 1})


def test_from_repair_steps_empty():
    with pytest.raises(ProvenanceError):
        from_repair_steps("x", {}, {}, [])


# -- ledger ----------------------------------------------------------------------
def test_ledger_chain_and_tamper_detection():
    led = ProvenanceLedger()
    h1 = led.append(gen())
    h2 = led.append(gen(artifact_id="quest-2"))
    assert h1 != h2 and led.head == h2
    entries = led.entries()
    assert ProvenanceLedger.verify(entries)
    assert len(led.lookup(digest({"q": 1}))) == 2
    entries[0]["record"]["model"] = "evil"
    with pytest.raises(ProvenanceError):
        ProvenanceLedger.verify(entries)
    with pytest.raises(ProvenanceError):
        ProvenanceLedger.verify(list(reversed(led.entries())))


def test_ledger_rejects_wrong_type():
    with pytest.raises(ProvenanceError):
        ProvenanceLedger().append(rec())  # type: ignore[arg-type]
