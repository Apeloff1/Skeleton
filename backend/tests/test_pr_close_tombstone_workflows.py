from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]

WORKFLOWS = {
    "dependency-security.yml": ("python-audit", "javascript-audit", "container-audit"),
    "dependency-surface-guard.yml": ("guard",),
    "deployment-trust.yml": ("deployment-trust",),
    "docker-secret-boundary.yml": ("boundary",),
    "durable-state.yml": ("durable-state",),
    "epistemic-finality.yml": ("epistemic-finality",),
    "execution-evidence.yml": ("evidence-lifecycle",),
    "gate-boundary-security.yml": ("boundary-regression",),
    "packaging-runtime-image.yml": ("packaging-contract", "docker-builds"),
    "reproducible-release.yml": ("reproducible-release",),
    "autonomous-studio-smoke.yml": ("smoke",),
    "epistemic-transparency.yml": ("transparency",),
    "idle-studio-validation.yml": ("validate",),
    "jeeves-absorb.yml": ("contract",),
    "jeeves-bidirectional.yml": ("focused-regression",),
    "jeeves-capability-evidence.yml": ("capability-evidence-contract",),
    "jeeves-game-engine-era-lab.yml": ("era-lab",),
    "jeeves-live-hardening.yml": ("focused-regression",),
    "jeeves-mode-compat.yml": ("compatibility",),
    "jeeves-predictive-evidence.yml": ("predictive-evidence",),
    "jeeves-probabilistic.yml": ("probabilistic-contracts",),
    "jeeves-session-resilience.yml": ("resilience",),
    "mined-primitives.yml": ("backend-worm-audit", "frontend-ui-verdict"),
    "mixture-depth.yml": ("adaptive-depth",),
    "portable-truth-proofs.yml": ("portable-truth-proofs",),
    "product-kernel.yml": ("backend-product-kernel", "frontend-product-contract"),
    "reliability-capacity-baseline.yml": ("baseline",),
    "route-coverage.yml": ("route-coverage",),
    "secret-store-security.yml": ("regression",),
    "swarm-durable-recovery.yml": ("swarm-durable-recovery",),
}


def _job_block(text: str, job: str) -> str:
    marker = f"\n  {job}:\n"
    assert marker in text
    start = text.index(marker) + 1
    remainder = text[start:]
    match = re.search(r"^  [A-Za-z0-9_-]+:\s*$", remainder[len(f"  {job}:\n"):], re.MULTILINE)
    if match is None:
        return remainder
    end = len(f"  {job}:\n") + match.start()
    return remainder[:end]


def test_pr_validation_workflows_use_zero_work_close_tombstones() -> None:
    for name, jobs in WORKFLOWS.items():
        text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        first_pr_child = text.split("  pull_request:\n", 1)[1].splitlines()[0]
        assert first_pr_child.strip().startswith("types:"), name
        assert "closed" in first_pr_child, name
        assert "cancel-in-progress: true" in text, name
        for job in jobs:
            assert "github.event.action != 'closed'" in _job_block(text, job), f"{name}: {job}"


def test_reproducible_release_uses_pr_number_for_close_cancellation_identity() -> None:
    text = (ROOT / ".github" / "workflows" / "reproducible-release.yml").read_text(
        encoding="utf-8"
    )
    assert (
        "group: reproducible-release-${{ github.workflow }}-"
        "${{ github.event.pull_request.number || github.ref }}"
    ) in text
    assert "group: reproducible-release-${{ github.workflow }}-${{ github.ref }}" not in text


def test_jeeves_absorb_does_not_put_sha_in_pr_concurrency_identity() -> None:
    text = (ROOT / ".github" / "workflows" / "jeeves-absorb.yml").read_text(
        encoding="utf-8"
    )
    assert "group: jeeves-absorb-${{ github.event.pull_request.number || github.ref }}" in text
    concurrency = text.split("concurrency:\n", 1)[1].split("\n\n", 1)[0]
    assert "github.sha" not in concurrency
