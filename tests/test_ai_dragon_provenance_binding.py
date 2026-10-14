"""Regression tests for provenance-authoritative evidence independence."""
import pytest
from skeleton.ai.webcrawler.dragon_probabilistic_distillation import (
    EvidencePass, ProbabilisticKnowledgeDistiller,
)
from skeleton.ai.webcrawler.dragon_provenance_binding import (
    bind_provenance_independence,
)
from skeleton.ai.webcrawler.dragon_source_independence import SourceProvenance


def ev(source, caller_group):
    return EvidencePass(
        source, "r1", "pass-1", "claim", True, .9, .9,
        caller_group, "frame:1", "observation",
    )


def prov(source, digest, uri):
    return SourceProvenance(source, digest * 64, uri)


def test_caller_cannot_manufacture_independence_for_copies():
    evidence = (ev("a", "caller-a"), ev("b", "caller-b"))
    provenance = (
        prov("a", "a", "https://one.example/original"),
        prov("b", "a", "https://two.example/copy"),
    )
    bound = bind_provenance_independence(
        evidence, provenance, authorized=True,
    )
    assert bound[0].independence_group == bound[1].independence_group
    belief = ProbabilisticKnowledgeDistiller().distill("claim", bound)
    assert belief.independent_groups == 1


def test_unrelated_sources_receive_distinct_derived_groups():
    bound = bind_provenance_independence(
        (ev("a", "same"), ev("b", "same")),
        (
            prov("a", "a", "https://a.example/a"),
            prov("b", "b", "https://b.example/b"),
        ),
        authorized=True,
    )
    assert bound[0].independence_group != bound[1].independence_group


def test_unknown_evidence_source_fails_closed():
    with pytest.raises(ValueError, match="missing provenance"):
        bind_provenance_independence(
            (ev("missing", "fake"),),
            (prov("a", "a", "https://a.example/a"),),
            authorized=True,
        )


def test_binding_is_deterministic():
    evidence = (ev("a", "x"), ev("b", "y"))
    provenance = (
        prov("a", "a", "https://a.example/a"),
        prov("b", "b", "https://b.example/b"),
    )
    assert bind_provenance_independence(
        evidence, provenance, authorized=True,
    ) == bind_provenance_independence(
        evidence, provenance, authorized=True,
    )


def test_binding_requires_authorization():
    with pytest.raises(PermissionError):
        bind_provenance_independence((), (), authorized=False)
