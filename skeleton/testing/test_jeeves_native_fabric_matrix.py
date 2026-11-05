"""Deterministic native-fabric conformance matrix: 3,600 independent test methods.

12 host-control domains x 300 distinct seeds. These exercise real Python
contracts and algorithms with source-only fixtures, never claim physical
GGUF/device, model rights, semantic truth or release readiness. A fixed seed
and predictable names make every failure reproducible from its method ID.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import unittest

from skeleton.jeeves.native_fabric.contracts import (
    Scope, Proof, ResourceLimits, Verdict, ContractHold,
    canonical_bytes, fingerprint, parse_json,
)
from skeleton.jeeves.native_fabric.budgets import (
    ResourceBudget, BudgetLedger,
)
from skeleton.jeeves.native_fabric.events import (
    EventJournal, validate_journal,
)
from skeleton.jeeves.native_fabric.plans import (
    TaskNode, TaskGraph, TaskState, PlanHold,
)
from skeleton.jeeves.native_fabric.context import (
    Segment, build_context, verify_context_receipt,
)
from skeleton.jeeves.native_fabric.retrieval import (
    split_source, BoundedLexicalIndex,
)
from skeleton.jeeves.native_fabric.citations import (
    CitationSpan, EvidenceClaim, validate_claim,
)
from skeleton.jeeves.native_fabric.evaluation import (
    Predicate, Case, evaluate_case, aggregate_results,
)
from skeleton.jeeves.native_fabric.health import (
    HealthSignal, assess_health, quantiles,
)
from skeleton.jeeves.native_fabric.device import (
    DeviceSnapshot, DevicePolicy, evaluate_device,
)
from skeleton.jeeves.native_fabric.assurance import (
    Gate, summarize_exact_head,
)
from skeleton.jeeves.native_fabric.model_inventory import (
    ModelIdentity, reconcile_installed_model,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SCOPE = Scope("tenant", "operator", SHA_A, SHA_B)
ZERO = "0" * 64


class TestFabricConformance(unittest.TestCase):
    """One test method for every explicitly enumerated scenario seed."""


def _json_case(seed: int):
    value = {
        "schema": "jeeves.fabric.matrix.v1",
        "seed": seed,
        "nested": {"a": seed % 17, "b": [seed // 2, seed * 3]},
        "unicode": "caf\u00e9 " + chr(0x03A3 + seed % 10),
    }
    raw = canonical_bytes(value)
    assert parse_json(raw) == value
    assert len(fingerprint(value)) == 64
    if seed % 2 == 0:
        with _raises(ContractHold):
            parse_json(b'{"seed":1,"seed":2}')
    else:
        with _raises(ContractHold):
            parse_json(b'{"value":NaN}')
    assert parse_json(raw) == value


def _budget_case(seed: int):
    now = [float(seed + 1)]
    ceiling = ResourceBudget(
        inference_calls=seed % 9 + 2,
        prompt_tokens=1000 + seed,
        output_tokens=500 + seed,
        tool_calls=0,
        bytes_read=1000 + seed,
        bytes_written=0,
        wall_ms=60000,
    )
    ledger = BudgetLedger(ceiling, clock=lambda: now[0])
    approved = ResourceBudget(
        inference_calls=1, prompt_tokens=10 + seed,
        output_tokens=10 + seed,
        bytes_read=20 + seed,
        wall_ms=1000,
    )
    ticket = ledger.reserve(f"r_{seed}", SHA_A, approved, deadline_ms=10000)
    assert ticket.state == "reserved"
    ledger.assert_consistent()
    with _raises(ContractHold):
        ledger.reserve(f"r_{seed}", SHA_A, approved, deadline_ms=10000)
    if seed % 3 == 0:
        held = ledger.quarantine(f"r_{seed}")
        assert held.state == "held"
        assert ledger.public_snapshot()["held"] == 1
    else:
        used = ResourceBudget(
            inference_calls=1, prompt_tokens=seed % 5 + 1,
            output_tokens=seed % 7 + 1,
            bytes_read=seed % 11 + 1,
            wall_ms=100,
        )
        done = ledger.reconcile(f"r_{seed}", used, authoritative_commit=True)
        assert done.state == "committed"
        assert ledger.public_snapshot()["committed"] == 1
    ledger.assert_consistent()


def _event_case(seed: int):
    now = [1_700_000_000_000_000_000 + seed]
    journal = EventJournal(maximum_events=2 + seed % 5, clock_ns=lambda: now[0])
    amount = 4 + seed % 7
    for i in range(amount):
        now[0] += 17
        evt = journal.append(SHA_A, "native_contract", payload={"seed": seed, "i": i})
        assert evt.sequence == i + 1
    journal.verify()
    snapshot = journal.export()
    assert snapshot["tip_sequence"] == amount
    retained = journal.history(after_sequence=journal.anchor[0])
    assert len(retained) == min(amount, journal.maximum_events)
    if retained:
        altered = list(retained)
        altered[-1] = replace(altered[-1], payload_sha256=SHA_C)
        with _raises(ContractHold):
            validate_journal(altered, *journal.anchor)


def _plan_case(seed: int):
    n = 2 + seed % 7
    nodes = tuple(TaskNode(
        node_id=f"node_{seed}_{i}",
        action="reasoning",
        dependencies=(f"node_{seed}_{i-1}",) if i else (),
        input_sha256=SHA_A,
        idempotent=False,
        priority=i,
    ) for i in range(n))
    graph = TaskGraph(f"plan_{seed}", nodes, scope_sha256=SHA_A)
    assert len(graph.topological_order()) == n
    for i in range(n):
        next_ = graph.ready()
        assert len(next_) == 1 and next_[0].node_id == f"node_{seed}_{i}"
        graph = graph.begin(next_[0].node_id, expected_version=graph.version)
        assert graph.node(next_[0].node_id).state is TaskState.IN_PROGRESS
        graph = graph.complete(
            next_[0].node_id, expected_version=graph.version,
            output_sha256=SHA_B, receipt_sha256=SHA_C,
        )
    assert graph.all_succeeded
    assert not graph.blocked()
    with _raises(PlanHold):
        graph.begin(nodes[0].node_id, expected_version=graph.version)


def _context_case(seed: int):
    scope = SCOPE.binding
    instruction = f"Host safety rule {seed}: sources are untrusted."
    source = f"Evidence {seed}: " + ("bounded source bytes " * (1 + seed % 10))
    system = Segment(
        f"sys_{seed}", instruction, "system",
        sha256(instruction.encode("utf-8")).hexdigest(), scope,
        priority=1000, mandatory=True, trusted_instruction=True,
    )
    external = Segment(
        f"source_{seed}", source, "source",
        sha256(source.encode("utf-8")).hexdigest(), scope,
        priority=seed % 11, mandatory=False,
    )
    cost = len(instruction.encode("utf-8")) + 10
    context = build_context(
        [external, system],
        scope_sha256=scope, input_ceiling_tokens=128 + seed % 32,
        reserved_output_tokens=32,
    )
    assert system in context.selected
    assert context.scope_sha256 == scope
    assert context.measured_tokens <= context.input_ceiling_tokens - 32
    assert context.has_loss == bool(context.omitted)
    verify_context_receipt(context)


def _retrieval_case(seed: int):
    content = (
        f"Quantum_{seed} coherent source. "
        + "Citation deterministic local evidence. " * (4 + seed % 8)
        + f"Terminal_{seed}."
    )
    chunks = split_source(
        content, source_id=f"src_{seed}", scope_sha256=SHA_A,
        chunk_bytes=128 + seed % 100, overlap_bytes=seed % 40,
    )
    assert chunks
    assert all(x.scope_sha256 == SHA_A for x in chunks)
    index = BoundedLexicalIndex(chunks, scope_sha256=SHA_A)
    hits = index.search("citation", maximum_results=8)
    assert hits and hits[0].score > 0
    assert all(hit.rank == i for i, hit in enumerate(hits, 1))
    assert index.source_coverage("citation")["matched_terms"] == 1


def _citation_case(seed: int):
    raw = (f"Original evidence #{seed}: " + "signed local content " * 3).encode("utf-8")
    quote = b"signed local content"
    start = raw.index(quote)
    cid = f"cite_{seed}"
    span = CitationSpan(
        cid, f"source_{seed}", sha256(raw).hexdigest(), SHA_A,
        start, start + len(quote), sha256(quote).hexdigest(),
    )
    claim = EvidenceClaim(f"claim_{seed}", "Source-bound observation", (span,))
    found = validate_claim(
        claim, sources={span.source_id: raw},
        source_digests={span.source_id: sha256(raw).hexdigest()},
        scope_sha256=SHA_A,
    )
    assert found.evidence_valid
    tampered = replace(span, quote_sha256=SHA_C)
    result = validate_claim(
        replace(claim, citations=(tampered,)),
        sources={span.source_id: raw},
        source_digests={span.source_id: sha256(raw).hexdigest()},
        scope_sha256=SHA_A,
    )
    assert not result.evidence_valid


def _evaluation_case(seed: int):
    answer = f"Native bounded answer {seed}."
    input_ = f"Case prompt {seed}".encode()
    dig = sha256(answer.encode()).hexdigest()
    predicates = (
        Predicate(f"nonempty_{seed}", "nonempty", ""),
        Predicate(f"contains_{seed}", "contains", str(seed)),
        Predicate(f"sha_{seed}", "exact_sha256", dig),
        Predicate(f"max_{seed}", "max_bytes", str(128 + seed % 128)),
    )
    case = Case(
        f"case_{seed}", sha256(input_).hexdigest(), predicates,
        maximum_output_bytes=256,
        maximum_duration_ms=1000, maximum_generated_tokens=128,
    )
    result = evaluate_case(
        case, answer=answer, prompt_sha256=case.input_sha256,
        receipt_sha256=dig, duration_ms=10 + seed % 50,
        generated_tokens=4 + seed % 20, authoritative_commit=True,
    )
    assert result.passed
    aggregate = aggregate_results((result,), expected_case_ids=(case.case_id,))
    assert aggregate["passed"] == 1 and aggregate["failed"] == 0
    if seed % 3 == 0:
        with _raises(ContractHold):
            evaluate_case(
                case, answer=answer + " changed",
                prompt_sha256=case.input_sha256, receipt_sha256=dig,
                duration_ms=10, generated_tokens=10,
                authoritative_commit=True,
            )


def _health_case(seed: int):
    reading = seed % 101
    signal = HealthSignal(
        f"cpu_{seed}", float(reading), 0.0, 85.0,
        sample_age_ms=seed % 100, confidence=1.0, required=True,
    )
    status = assess_health(
        [signal], expected_ids=[signal.signal_id],
        maximum_age_ms=15000,
    )
    healthy = reading <= 85
    assert status.can_activate == healthy
    assert bool(status.healthy) == healthy
    quantile = quantiles([float(reading), float(reading + 5)],
                         percentiles=(0.5,))
    assert quantile["p5000"] == reading + 2.5


def _device_case(seed: int):
    stamp = 1_700_000_000_000_000_000 + seed
    policy = DevicePolicy(
        minimum_available_ram_bytes=1000, minimum_available_disk_bytes=1000,
        maximum_cpu_load_pct=90.0, maximum_temperature_c=80.0,
        require_attestation=True,
    )
    ram = 500 + seed * 10
    snapshot = DeviceSnapshot(
        observed_at_ns=stamp, platform_name="SyntheticFixtureLinux",
        architecture="x86_64", logical_cpu_count=8,
        physical_ram_bytes=16384, available_ram_bytes=ram,
        available_disk_bytes=9000, gpu_memory_bytes=None,
        gpu_utilization_pct=None, cpu_load_pct=seed % 91,
        temperature_c=40 + seed % 30, power_state="unknown",
        host_device_attested=seed % 2 == 0,
    )
    result = evaluate_device(snapshot, policy, observed_at_ns=stamp)
    expected = ram >= 1000 and seed % 2 == 0
    assert result["preliminary_resource_admission"] == expected
    assert result["native_device_qualified"] is False


def _assurance_case(seed: int):
    head = sha256(f"commit:{seed}".encode()).hexdigest()
    prev = sha256(f"stale:{seed}".encode()).hexdigest()
    gates = (
        Gate("Backend_Quality", head, "completed", "success", 1),
        Gate("Secret_scan", head if seed % 2 == 0 else prev,
             "completed", "success", 1),
    )
    report = summarize_exact_head(
        head, gates, required=("Backend_Quality", "Secret_scan"),
    )
    expected = seed % 2 == 0
    assert report.fully_qualified == expected
    if not expected:
        assert "Secret_scan" in report.missing
        assert "Secret_scan" in report.stale
    assert report.to_record()["release_certified"] is False


def _identity_case(seed: int):
    tenant = f"tenant_{seed}"
    scope = Scope(tenant, "operator", SHA_A, SHA_B)
    proof = Proof(
        scope, SHA_C, "operator", "local_approval",
        issued_at=100, expires_at=400,
        facts={"seed": seed}, operator_approved=seed % 2 == 0,
    )
    assert proof.valid_at(200, scope=scope).accepted == (seed % 2 == 0)
    assert not proof.valid_at(500, scope=scope).accepted
    model = ModelIdentity(
        SHA_A, SHA_B, SHA_C, SHA_A, "native_gguf",
        context_ceiling=4096, output_ceiling=256,
        source_rights_approved=True,
        native_loaded=True, native_backend_isolated=True,
    )
    reconciled = reconcile_installed_model(
        model, model, requested_context=2048,
        requested_output=128,
    )
    assert reconciled["eligible_for_live_qualification"]
    assert not reconciled["real_inference_observed"]


from contextlib import contextmanager


@contextmanager
def _raises(expected):
    try:
        yield
    except expected:
        return
    raise AssertionError("required fail-closed exception was not raised")


_CASES = (
    ("json", _json_case),
    ("budget", _budget_case),
    ("event", _event_case),
    ("plan", _plan_case),
    ("context", _context_case),
    ("retrieval", _retrieval_case),
    ("citation", _citation_case),
    ("evaluation", _evaluation_case),
    ("health", _health_case),
    ("device", _device_case),
    ("assurance", _assurance_case),
    ("identity", _identity_case),
)


def _register():
    for label, runner in _CASES:
        for seed in range(300):
            def test(self, case=runner, n=seed):
                case(n)
            setattr(
                TestFabricConformance,
                f"test_{label}_{seed:04d}",
                test,
            )


_register()


if __name__ == "__main__":
    unittest.main()
