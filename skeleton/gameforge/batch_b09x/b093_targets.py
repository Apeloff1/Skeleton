"""B093: desktop/mobile/web target matrix: capabilities, budgets, recipes, smoke tests."""

from __future__ import annotations

from dataclasses import dataclass

from ._helpers import ContractError, require, verdict

__all__ = ["ContractError", "MATRIX", "Target", "evaluate"]


@dataclass(frozen=True)
class Target:
    name: str
    family: str
    capabilities: frozenset[str]
    max_mb: int
    frame_ms: float
    recipe: tuple[str, ...]


MATRIX: dict[str, Target] = {
    t.name: t
    for t in (
        Target(
            "windows-x64",
            "desktop",
            frozenset({"gamepad", "keyboard", "threads", "gpu_compute"}),
            2048,
            16.6,
            ("export", "--preset", "Windows Desktop"),
        ),
        Target(
            "linux-x64",
            "desktop",
            frozenset({"gamepad", "keyboard", "threads", "gpu_compute"}),
            2048,
            16.6,
            ("export", "--preset", "Linux"),
        ),
        Target(
            "macos-universal",
            "desktop",
            frozenset({"gamepad", "keyboard", "threads"}),
            2048,
            16.6,
            ("export", "--preset", "macOS"),
        ),
        Target(
            "android-arm64",
            "mobile",
            frozenset({"touch", "gamepad", "threads"}),
            150,
            33.3,
            ("export", "--preset", "Android"),
        ),
        Target(
            "ios-arm64",
            "mobile",
            frozenset({"touch", "gamepad", "threads"}),
            200,
            33.3,
            ("export", "--preset", "iOS"),
        ),
        Target(
            "web-wasm",
            "web",
            frozenset({"keyboard", "touch", "gamepad"}),
            50,
            33.3,
            ("export", "--preset", "Web"),
        ),
    )
}


def evaluate(
    target: str, needs: set[str], size_mb: int, p95_frame_ms: float, smoke_passed: bool
):
    require(target in MATRIX, f"unknown target {target}")
    t = MATRIX[target]
    findings = [f"missing_capability:{c}" for c in sorted(needs - t.capabilities)]
    if size_mb > t.max_mb:
        findings.append(f"size:{size_mb}>{t.max_mb}")
    if p95_frame_ms > t.frame_ms:
        findings.append(f"frame:{p95_frame_ms}>{t.frame_ms}")
    if not smoke_passed:
        findings.append("smoke")
    return verdict("B093", findings, target=target, recipe=list(t.recipe))
