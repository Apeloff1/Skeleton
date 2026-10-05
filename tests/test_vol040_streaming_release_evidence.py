from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/p1-streaming-projection-authority.yml"
TRANSPORT_TEST = ROOT / "backend/tests/test_operation_stream_transport.py"
FRONTEND_TEST = ROOT / "frontend/scripts/test-operation-stream-reducer.mjs"
FRONTEND_REDUCER = ROOT / "frontend/services/operationStreamReducer.ts"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_canonical_streaming_gate_triggers_on_frontend_reducer_authority() -> None:
    workflow = _text(WORKFLOW)

    assert workflow.count(
        '"frontend/services/operationStreamReducer.ts"'
    ) >= 2
    assert workflow.count(
        '"frontend/scripts/test-operation-stream-reducer.mjs"'
    ) >= 2
    assert workflow.count('"frontend/package.json"') >= 2


def test_canonical_streaming_gate_executes_frontend_reducer_regressions() -> None:
    workflow = _text(WORKFLOW)

    assert (
        "node --test frontend/scripts/test-operation-stream-reducer.mjs"
        in workflow
    )
    assert (
        "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020"
        in workflow
    )
    assert 'node-version: "24"' in workflow


def test_frontend_reducer_is_bound_into_exact_head_promotion_evidence() -> None:
    workflow = _text(WORKFLOW)

    required = (
        '"frontend/services/operationStreamReducer.ts"',
        '"frontend/scripts/test-operation-stream-reducer.mjs"',
        '"frontend_stream_reducer_verification"',
        '"frontend:operation-stream-reducer:"',
        'os.environ["EXPECTED_SHA"]',
        '["node", "--version"]',
    )
    for token in required:
        assert token in workflow

    # The source belongs to verifier identity, while its executable regression
    # belongs to test-manifest identity. This prevents a passing Node command
    # from being detached from the exact reducer implementation it verified.
    verifier_start = workflow.index(
        'Path(".p1-prod-02/verifier.digest").write_text('
    )
    tests_start = workflow.index(
        'Path(".p1-prod-02/tests.digest").write_text('
    )
    verifier_block = workflow[verifier_start:tests_start]
    tests_block = workflow[tests_start:]

    assert '"frontend/services/operationStreamReducer.ts"' in verifier_block
    assert (
        '"frontend/scripts/test-operation-stream-reducer.mjs"'
        in tests_block
    )


def test_multi_client_compaction_proof_remains_materialized() -> None:
    transport = _text(TRANSPORT_TEST)

    start = transport.index(
        "def test_acknowledge_and_compact_waits_for_slowest_active_consumer"
    )
    block = transport[start : start + 3200]

    required = (
        'consumer_id="client-a"',
        'consumer_id="client-b"',
        "assert fast.compacted_through == 0",
        "assert fast.compacted_events == 0",
        "assert fast.active_consumer_count == 2",
        "assert slow.compacted_through == 2",
        "assert slow.compacted_events == 2",
        "with pytest.raises(StreamReplayGapError)",
        "after_sequence=1",
    )
    for token in required:
        assert token in block


def test_frontend_reducer_proves_cursor_reconnect_and_terminal_reconciliation() -> None:
    test_source = _text(FRONTEND_TEST)
    reducer_source = _text(FRONTEND_REDUCER)

    required_tests = (
        "persisted cursor keys are isolated per consumer identity",
        "disconnect and reconnect replay pages preserve exact accepted cursor continuity",
        "slow-client page gaps fail closed instead of skipping retained work",
        "cancel-complete race is terminal-fenced in both arrival orders",
        "completed terminal replaces provisional display with canonical output",
    )
    for title in required_tests:
        assert title in test_source

    required_reducer_contract = (
        "operationCursorStorageKey",
        "reduceOperationEvent",
        "reduceOperationReplay",
        "resyncRequired",
        "lastSequence",
        "seenEventIds",
    )
    for token in required_reducer_contract:
        assert token in reducer_source
