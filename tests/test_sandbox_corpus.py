"""B086 injection fuzz corpus: determinism, bounds, gate and detector quality."""
from __future__ import annotations

import json

import pytest

from skeleton.sandbox import ATTACK_SEEDS, BENIGN_SEEDS, CorpusGateError, CorpusReport, assert_gate, evaluate, fuzz
from skeleton.sandbox.corpus import MUTATORS, main


def test_seed_counts() -> None:
    assert len(ATTACK_SEEDS) >= 25 and len(BENIGN_SEEDS) >= 10
    assert len({s.case_id for s in (*ATTACK_SEEDS, *BENIGN_SEEDS)}) == len(ATTACK_SEEDS) + len(BENIGN_SEEDS)
    assert len(MUTATORS) >= 16


def test_fuzz_is_deterministic() -> None:
    assert list(fuzz()) == list(fuzz())


def test_fuzz_seed_changes_output() -> None:
    assert [c.payload for c in fuzz(seed=1)] != [c.payload for c in fuzz(seed=2)]


def test_fuzz_flags_maliciousness() -> None:
    assert all(c.malicious for c in fuzz())
    assert not any(c.malicious for c in fuzz(BENIGN_SEEDS, malicious=False))


def test_unknown_mutator_rejected() -> None:
    with pytest.raises(CorpusGateError):
        list(fuzz(mutators=["does-not-exist"]))


@pytest.mark.parametrize("name", sorted(MUTATORS))
def test_each_mutator_returns_text(name: str) -> None:
    cases = list(fuzz(mutators=[name], rounds=1))
    assert cases and all(isinstance(c.payload, str) and c.payload for c in cases)


def test_full_corpus_clears_gate() -> None:
    report = evaluate()
    assert report.recall == 1.0
    assert report.false_positives == 0 and report.total_benign > 0
    assert not report.errors
    assert assert_gate(report) is report


def test_gate_fails_on_blind_detector() -> None:
    class _Blind:
        score = 0.0
        families: list[str] = []

    report = evaluate(detector=lambda text, context="any": _Blind())
    assert report.recall == 0.0
    with pytest.raises(CorpusGateError):
        assert_gate(report)


def test_erroring_detector_fails_closed() -> None:
    def boom(text, context="any"):
        raise RuntimeError("x")

    report = evaluate(detector=boom)
    assert report.errors and report.recall == 0.0


def test_report_record_shape() -> None:
    rec = CorpusReport(threshold=0.4).to_record()
    assert rec["recall"] == 0.0 and rec["false_positive_rate"] == 0.0


def test_cli_prints_json_and_passes(capsys) -> None:
    assert main([]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True and data["report"]["recall"] == 1.0
