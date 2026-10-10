"""Operator-runnable offline application acceptance, not model promotion.

Use the *same* bounded native inference, real CPU training and artifact,
transcript, and category benchmark smokes exercised by Windows CI. This is
a release-installation functionality receipt; it never means that a native
fixture is a useful pretrained language model or a tested remote GGUF engine.

Intentionally avoids self-installation, background work, network calls, model
downloads, hidden providers, or changing persistent user checkpoints.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

ACCEPTANCE_SCHEMA = "skeleton.app.local_ai.acceptance.v1"


@dataclass(frozen=True, slots=True)
class OfflineAcceptanceStep:
    name: str
    passed: bool
    failure_kind: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "failure_kind": self.failure_kind,
        }


def run_offline_acceptance() -> dict[str, object]:
    """Execute real bounded local model operations in disposable storage.

    Error strings can contain local paths or source excerpts. Emit only the
    exception class for failed checks so diagnostics cannot leak private data.
    """
    from skeleton.app.local_ai import smoke_offline_native_inference
    from skeleton.app.local_ai_training import smoke_offline_native_training
    from skeleton.app.local_ai_benchmark import smoke_offline_native_benchmark

    checks: tuple[tuple[str, Callable[[], bool]], ...] = (
        ("native_inference_and_transcript", smoke_offline_native_inference),
        ("cpu_gradient_checkpoint_and_inference", smoke_offline_native_training),
        ("category_benchmark_and_model_identity", smoke_offline_native_benchmark),
    )
    outcome: list[OfflineAcceptanceStep] = []
    for name, check in checks:
        try:
            result = check()
            if type(result) is not bool:
                outcome.append(OfflineAcceptanceStep(name, False, "InvalidCheckResult"))
            else:
                outcome.append(OfflineAcceptanceStep(
                    name, result, None if result else "CheckReturnedFalse",
                ))
        except Exception as exc:
            outcome.append(OfflineAcceptanceStep(name, False, type(exc).__name__))
    passed = len(outcome) == len(checks) and all(item.passed for item in outcome)
    return {
        "schema": ACCEPTANCE_SCHEMA,
        "passed": passed,
        "checks": [item.to_dict() for item in outcome],
        "checks_passed": sum(item.passed for item in outcome),
        "checks_total": len(checks),
        "persistent_user_artifacts_modified": False,
        "network_requested_by_selfcheck": False,
        "external_model_downloaded": False,
        "hosted_provider_used": False,
        "general_model_quality_certified": False,
        "enterprise_release_qualified": False,
        "independent_security_certified": False,
        "gguf_model_qualified": False,
        "purpose": "bounded packaged-native functionality, not general model capability",
    }
