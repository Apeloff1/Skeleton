"""Public import contract for the bounded shell orchestration slice."""

from skeleton import shells


def test_shell_public_surface_exports_core_orchestration_contract() -> None:
    expected = {
        "CommandAdmission",
        "CommandCatalog",
        "ShellControlPlane",
        "ShellExecutor",
        "ShellRunner",
        "ShellWorkQueue",
        "PipelineExecutor",
        "PreflightAnalyzer",
        "RateLimiter",
        "ReceiptChain",
        "ShellSession",
        "ShellTelemetry",
        "ShellToolAdapter",
        "QueueWorker",
    }
    missing = sorted(name for name in expected if not hasattr(shells, name))
    assert missing == []
    assert expected <= set(shells.__all__)


def test_shell_public_surface_has_no_duplicate_exports() -> None:
    assert len(shells.__all__) == len(set(shells.__all__))
