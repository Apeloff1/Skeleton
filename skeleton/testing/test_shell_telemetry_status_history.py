from datetime import datetime, timezone
from pathlib import Path
import sys

from skeleton.shells.circuit import CircuitPolicy, CircuitRegistry
from skeleton.shells.history import HistoryQuery, ReceiptHistory
from skeleton.shells.receipts import ExecutionReceipt, ReceiptChain
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.status import status_snapshot
from skeleton.shells.telemetry import ShellTelemetry


def receipt(command="python", ok=True, correlation="c", attempt=1):
    now = datetime.now(timezone.utc).isoformat()
    return ExecutionReceipt(
        command=command,
        correlation_id=correlation,
        fingerprint="f",
        started_at=now,
        finished_at=now,
        duration_ms=2,
        returncode=0 if ok else 1,
        ok=ok,
        timed_out=False,
        output_limited=False,
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=attempt,
    )


def test_telemetry_aggregates_success_and_failure():
    telemetry = ShellTelemetry()
    telemetry.started("python")
    telemetry.completed("python", ok=True, timed_out=False, output_limited=False, stdout_bytes=10, stderr_bytes=0, duration_ms=5)
    telemetry.started("python")
    telemetry.completed("python", ok=False, timed_out=True, output_limited=False, stdout_bytes=0, stderr_bytes=3, duration_ms=15)
    metric = telemetry.snapshot()["python"]
    assert metric.started == 2
    assert metric.completed == 2
    assert metric.failed == 1
    assert metric.timed_out == 1
    assert metric.average_duration_ms == 10


def test_telemetry_bounds_command_cardinality():
    telemetry = ShellTelemetry(max_commands=1)
    telemetry.started("a")
    telemetry.started("b")
    snapshot = telemetry.snapshot()
    assert "a" in snapshot
    assert "[overflow]" in snapshot


def test_telemetry_reset_clears_metrics():
    telemetry = ShellTelemetry()
    telemetry.started("python")
    telemetry.reset()
    assert telemetry.snapshot() == {}


def test_history_is_bounded_and_newest_first():
    history = ReceiptHistory(max_receipts=2)
    history.append(receipt(correlation="one"))
    history.append(receipt(correlation="two"))
    history.append(receipt(correlation="three"))
    assert history.count() == 2
    assert [item.correlation_id for item in history.query()] == ["three", "two"]


def test_history_filters_by_command_ok_correlation_and_attempt():
    history = ReceiptHistory()
    history.extend(
        [
            receipt("python", True, "x", 1),
            receipt("git", False, "x", 2),
            receipt("python", False, "y", 3),
        ]
    )
    assert len(history.query(HistoryQuery(command="python"))) == 2
    assert len(history.query(HistoryQuery(ok=False))) == 2
    assert len(history.query(HistoryQuery(correlation_id="x"))) == 2
    assert len(history.query(HistoryQuery(min_attempt=2))) == 2
    assert history.commands() == ("git", "python")


def test_status_snapshot_combines_health_metrics_circuits_and_receipts(tmp_path):
    policy = ShellPolicy(executables={"python": str(Path(sys.executable).resolve())}, cwd_roots=(tmp_path,))
    runner = ShellRunner(policy)
    telemetry = ShellTelemetry()
    telemetry.started("python")
    telemetry.completed("python", ok=True, timed_out=False, output_limited=False, stdout_bytes=1, stderr_bytes=0, duration_ms=1)
    circuits = CircuitRegistry()
    circuits.get("python")
    chain = ReceiptChain()
    chain.append(receipt())
    status = status_snapshot(runner, telemetry, circuits, chain)
    assert status.healthy
    assert status.receipt_chain_valid is True
    assert status.receipt_root == chain.root_hash()
    assert status.metrics["python"]["completed"] == 1


def test_status_snapshot_marks_open_circuit_unhealthy(tmp_path):
    policy = ShellPolicy(executables={"python": str(Path(sys.executable).resolve())}, cwd_roots=(tmp_path,))
    circuits = CircuitRegistry(CircuitPolicy(failure_threshold=1, recovery_seconds=1000))
    circuits.get("python").record_failure()
    status = status_snapshot(ShellRunner(policy), ShellTelemetry(), circuits)
    assert not status.healthy
