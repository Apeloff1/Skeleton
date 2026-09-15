from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_docker_context_hygiene.py"
SPEC = importlib.util.spec_from_file_location("check_docker_context_hygiene", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def _write_policy(path: Path, *extra_rules: str, omit: str | None = None) -> None:
    rules = [rule for rule in CHECK.REQUIRED_RULES if rule != omit]
    rules.extend(extra_rules)
    path.write_text("\n".join(rules) + "\n", encoding="utf-8")


def test_required_frontend_docker_secret_boundary_passes(tmp_path: Path) -> None:
    dockerignore = tmp_path / ".dockerignore"
    _write_policy(dockerignore)

    assert CHECK.violations(dockerignore) == []


def test_missing_required_secret_exclusion_is_reported(tmp_path: Path) -> None:
    dockerignore = tmp_path / ".dockerignore"
    _write_policy(dockerignore, omit="*.key")

    findings = CHECK.violations(dockerignore)

    assert len(findings) == 1
    assert findings[0].endswith("missing required secret exclusion: *.key")


def test_unapproved_negation_is_rejected(tmp_path: Path) -> None:
    dockerignore = tmp_path / ".dockerignore"
    _write_policy(dockerignore, "!developer-secret.key")

    findings = CHECK.violations(dockerignore)

    assert len(findings) == 1
    assert findings[0].endswith("unapproved Dockerignore negation: !developer-secret.key")


def test_missing_dockerignore_fails_closed(tmp_path: Path) -> None:
    findings = CHECK.violations(tmp_path / "missing.dockerignore")

    assert len(findings) == 1
    assert findings[0].endswith("read failure: FileNotFoundError")


def test_repository_frontend_dockerignore_satisfies_policy() -> None:
    assert CHECK.violations() == []
