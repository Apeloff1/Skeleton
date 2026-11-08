"""VOL-250 executable regression coverage: causal provenance and simulation safety."""
from __future__ import annotations

from dataclasses import replace
import math
import unittest

from skeleton.ai.research.causal_knowledge import (
    CausalClaim, CausalGraph, CausalKnowledgeError, ClaimKind,
)
from skeleton.ai.research.source_lineage import ResearchSourceRegistry, SourceStatus


def _source(reg: ResearchSourceRegistry, name: str) -> str:
    reg.ingest(
        source_id=name,
        uri="https://example.invalid/" + name,
        content="audited causal evidence " + name,
        rights_refs=("rights:test-fixture",),
    )
    return reg.source(name).content_digest


def _claim(
    name: str, cause: str, effect: str, source: str, digest: str, *,
    kind: ClaimKind = ClaimKind.IDENTIFIED_MODEL,
    coefficient: float | None = 0.5,
    confounders: tuple[str, ...] = (),
) -> CausalClaim:
    return CausalClaim(
        name, cause, effect, source, digest,
        "pre-registered controlled design", kind,
        ("linear structural equations", "stable treatment assumptions"),
        confounders,
        coefficient if kind is not ClaimKind.ASSOCIATION else None,
    )


class TestCausalKnowledge(unittest.TestCase):
    def setUp(self) -> None:
        self.sources = ResearchSourceRegistry()
        self.graph = CausalGraph(self.sources)

    def test_intervention_is_bounded_reproducible_and_never_observed(self):
        d1 = _source(self.sources, "SRC.A")
        d2 = _source(self.sources, "SRC.B")
        d3 = _source(self.sources, "SRC.C")
        self.graph.add(_claim("EDGE.AB", "A", "B", "SRC.A", d1, coefficient=0.5))
        self.graph.add(_claim("EDGE.BC", "B", "C", "SRC.B", d2, coefficient=0.3))
        self.graph.add(_claim("EDGE.AC", "A", "C", "SRC.C", d3, coefficient=0.2))
        result = self.graph.simulate("A", 2.0)
        self.assertEqual(result.result_kind, "SIMULATION_NOT_OBSERVATION")
        self.assertFalse(result.observed)
        self.assertEqual(dict(result.simulated_deltas), {"A": 2.0, "B": 1.0, "C": 0.7})
        self.assertEqual(len(result.model_claim_ids), 3)
        self.assertEqual(result.receipt_digest, self.graph.simulate("A", 2.0).receipt_digest)
        self.assertEqual(len(self.graph.snapshot().receipt_digest), 64)

    def test_association_not_promoted_to_structural_causation(self):
        digest = _source(self.sources, "SRC.A")
        claim = _claim("EDGE.AB", "A", "B", "SRC.A", digest,
                       kind=ClaimKind.ASSOCIATION)
        self.graph.add(claim)
        self.assertEqual(self.graph.snapshot().causal_claim_ids, ())
        self.assertEqual(self.graph.snapshot().association_claim_ids, ("EDGE.AB",))
        result = self.graph.simulate("A", 3)
        self.assertEqual(result.simulated_deltas, (("A", 3.0),))
        self.assertEqual(result.model_claim_ids, ())

    def test_hypothesized_edges_require_explicit_opt_in(self):
        digest = _source(self.sources, "SRC.A")
        self.graph.add(_claim("EDGE.AB", "A", "B", "SRC.A", digest,
                              kind=ClaimKind.CAUSAL_HYPOTHESIS))
        with self.assertRaisesRegex(CausalKnowledgeError, "opt-in"):
            self.graph.simulate("A", 1.0)
        result = self.graph.simulate("A", 1.0, allow_hypothesized=True)
        self.assertIn(("B", 0.5), result.simulated_deltas)
        self.assertFalse(result.observed)

    def test_unresolved_confounders_prohibit_intervention(self):
        digest = _source(self.sources, "SRC.A")
        self.graph.add(_claim("EDGE.AB", "A", "B", "SRC.A", digest,
                              confounders=("selection-bias",)))
        with self.assertRaisesRegex(CausalKnowledgeError, "confounders"):
            self.graph.simulate("A", 1.0)
        # Mere opt-in for hypotheses never bypasses confounder requirements.
        with self.assertRaisesRegex(CausalKnowledgeError, "confounders"):
            self.graph.simulate("A", 1.0, allow_hypothesized=True)

    def test_causal_cycle_is_rejected_transactionally(self):
        d1, d2 = _source(self.sources, "SRC.A"), _source(self.sources, "SRC.B")
        self.graph.add(_claim("EDGE.AB", "A", "B", "SRC.A", d1))
        before = self.graph.snapshot()
        with self.assertRaisesRegex(CausalKnowledgeError, "cycle"):
            self.graph.add(_claim("EDGE.BA", "B", "A", "SRC.B", d2))
        self.assertEqual(before, self.graph.snapshot())

    def test_bidirectional_observational_associations_do_not_create_causal_cycle(self):
        d1, d2 = _source(self.sources, "SRC.A"), _source(self.sources, "SRC.B")
        self.graph.add(_claim("ASSOC.AB", "A", "B", "SRC.A", d1,
                              kind=ClaimKind.ASSOCIATION))
        self.graph.add(_claim("ASSOC.BA", "B", "A", "SRC.B", d2,
                              kind=ClaimKind.ASSOCIATION))
        self.assertEqual(len(self.graph.snapshot().association_claim_ids), 2)
        self.assertEqual(self.graph.simulate("A", 1).model_claim_ids, ())

    def test_identical_identity_replay_or_conflict(self):
        digest = _source(self.sources, "SRC.A")
        claim = _claim("EDGE.AB", "A", "B", "SRC.A", digest)
        first = self.graph.add(claim)
        self.assertEqual(first, self.graph.add(claim))
        with self.assertRaisesRegex(CausalKnowledgeError, "identity conflict"):
            self.graph.add(replace(claim, coefficient=0.9))
        self.assertEqual(self.graph.snapshot().causal_claim_ids, ("EDGE.AB",))

    def test_parallel_structural_edges_must_be_reconciled_not_silently_averaged(self):
        d1, d2 = _source(self.sources, "SRC.A"), _source(self.sources, "SRC.B")
        self.graph.add(_claim("EDGE.AB", "A", "B", "SRC.A", d1))
        with self.assertRaisesRegex(CausalKnowledgeError, "duplicate structural"):
            self.graph.add(_claim("EDGE.AB.TWO", "A", "B", "SRC.B", d2))
        self.assertEqual(len(self.graph.snapshot().causal_claim_ids), 1)

    def test_retracted_sources_invalidate_graph_and_simulation(self):
        digest = _source(self.sources, "SRC.A")
        self.graph.add(_claim("EDGE.AB", "A", "B", "SRC.A", digest))
        self.sources.transition_source_status(
            "SRC.A", status=SourceStatus.RETRACTED,
            correction_refs=("notice:retract",),
        )
        with self.assertRaisesRegex(CausalKnowledgeError, "retracted"):
            self.graph.snapshot()
        with self.assertRaisesRegex(CausalKnowledgeError, "retracted"):
            self.graph.simulate("A", 1)

    def test_unknown_source_and_digest_mismatch_fail_closed(self):
        with self.assertRaisesRegex(CausalKnowledgeError, "unknown"):
            self.graph.add(_claim("EDGE.AB", "A", "B", "SRC.A", "f" * 64))
        _source(self.sources, "SRC.A")
        with self.assertRaisesRegex(CausalKnowledgeError, "digest mismatch"):
            self.graph.add(_claim("EDGE.AB", "A", "B", "SRC.A", "f" * 64))

    def test_invalid_claims_and_nonfinite_coefficients_rejected(self):
        digest = "a" * 64
        for coefficient in (math.nan, math.inf, True, 2.01, -2.01):
            with self.subTest(coefficient=coefficient):
                with self.assertRaises(CausalKnowledgeError):
                    _claim("EDGE.AB", "A", "B", "SRC.A", digest,
                           coefficient=coefficient)
        with self.assertRaisesRegex(CausalKnowledgeError, "self-causation"):
            _claim("EDGE.AA", "A", "A", "SRC.A", digest)
        with self.assertRaisesRegex(CausalKnowledgeError, "association"):
            CausalClaim("EDGE.AB", "A", "B", "SRC.A", digest,
                        "method", ClaimKind.ASSOCIATION, ("assumption",),
                        (), 0.5)
        with self.assertRaisesRegex(CausalKnowledgeError, "assumptions"):
            CausalClaim("EDGE.AB", "A", "B", "SRC.A", digest,
                        "method", ClaimKind.IDENTIFIED_MODEL, (), (), 0.5)

    def test_numeric_and_capacity_budgets(self):
        digest = _source(self.sources, "SRC.A")
        graph = CausalGraph(self.sources, max_nodes=2, max_claims=1)
        graph.add(_claim("EDGE.AB", "A", "B", "SRC.A", digest))
        with self.assertRaisesRegex(CausalKnowledgeError, "capacity"):
            graph.add(_claim("EDGE.BC", "B", "C", "SRC.A", digest))
        for value in (float("nan"), math.inf, -11, 11, True):
            with self.subTest(value=value), self.assertRaises(CausalKnowledgeError):
                graph.simulate("A", value)
        with self.assertRaisesRegex(CausalKnowledgeError, "boolean"):
            graph.simulate("A", 1.0, allow_hypothesized=1)
        with self.assertRaisesRegex(CausalKnowledgeError, "max_nodes"):
            CausalGraph(self.sources, max_nodes=0)

    def test_runaway_effect_magnitude_fails_closed(self):
        # A long DAG with coefficient 2 can numerically explode.
        graph = CausalGraph(self.sources, max_nodes=32)
        for i in range(15):
            name = "SRC." + str(i)
            digest = _source(self.sources, name)
            graph.add(_claim(
                "EDGE." + str(i),
                "VAR." + str(i), "VAR." + str(i + 1),
                name, digest, coefficient=2.0,
            ))
        with self.assertRaisesRegex(CausalKnowledgeError, "bounded model magnitude"):
            graph.simulate("VAR.0", 10.0)

    def test_deterministic_snapshot_and_simulation_independent_of_insert_order(self):
        d1, d2 = _source(self.sources, "SRC.A"), _source(self.sources, "SRC.B")
        a = _claim("EDGE.AB", "A", "B", "SRC.A", d1, coefficient=0.25)
        b = _claim("EDGE.BC", "B", "C", "SRC.B", d2, coefficient=0.75)
        first, second = CausalGraph(self.sources), CausalGraph(self.sources)
        first.add(a); first.add(b)
        second.add(b); second.add(a)
        self.assertEqual(first.snapshot(), second.snapshot())
        self.assertEqual(first.simulate("A", 1), second.simulate("A", 1))

    def test_unrelated_hypothesized_edge_does_not_block_scoped_intervention(self):
        d1, d2 = _source(self.sources, "SRC.A"), _source(self.sources, "SRC.B")
        self.graph.add(_claim("EDGE.AB", "A", "B", "SRC.A", d1))
        self.graph.add(_claim("EDGE.XY", "X", "Y", "SRC.B", d2,
                              kind=ClaimKind.CAUSAL_HYPOTHESIS))
        self.assertEqual(dict(self.graph.simulate("A", 1).simulated_deltas),
                         {"A": 1.0, "B": 0.5})

    def test_empty_graph_has_explicitly_simulated_baseline_delta_only(self):
        result = self.graph.simulate("A", 1)
        self.assertEqual(result.simulated_deltas, (("A", 1.0),))
        self.assertEqual(result.model_claim_ids, ())
        self.assertFalse(result.observed)


    def test_unbounded_integer_coefficient_is_denied_by_contract(self):
        digest = _source(self.sources, "SRC.OVERFLOW")
        with self.assertRaises(CausalKnowledgeError):
            self.graph.add(_claim(
                "EDGE.OVERFLOW", "A", "B", "SRC.OVERFLOW", digest,
                coefficient=10 ** 1000,
            ))

if __name__ == "__main__":
    unittest.main()
