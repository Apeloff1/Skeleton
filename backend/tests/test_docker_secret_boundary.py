from __future__ import annotations

from pathlib import Path

from scripts import check_docker_secret_boundary as docker_boundary


REPO_ROOT = Path(__file__).resolve().parents[2]


def _policy() -> docker_boundary.DockerContextPolicy:
    return docker_boundary.DockerContextPolicy(
        dockerfile=Path("frontend/Dockerfile"),
        ignore_file=Path("frontend/.dockerignore"),
    )


def _complete_ignore_text() -> str:
    patterns = sorted(
        docker_boundary.REQUIRED_SECRET_EXCLUSIONS
        | docker_boundary.REQUIRED_REINCLUSIONS
    )
    return "\n".join(patterns) + "\n"


def _write_broad_context(tmp_path: Path, ignore_text: str | None) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "Dockerfile").write_text(
        "FROM node:alpine\nWORKDIR /app\nCOPY . .\n",
        encoding="utf-8",
    )
    if ignore_text is not None:
        (frontend / ".dockerignore").write_text(ignore_text, encoding="utf-8")


def test_current_frontend_docker_context_secret_boundary_is_complete() -> None:
    assert docker_boundary.policy_violations(_policy(), repo_root=REPO_ROOT) == []


def test_missing_dockerignore_fails_closed(tmp_path: Path) -> None:
    _write_broad_context(tmp_path, None)

    findings = docker_boundary.policy_violations(_policy(), repo_root=tmp_path)

    assert findings == ["frontend/.dockerignore: read failure: FileNotFoundError"]


def test_missing_required_secret_exclusion_is_rejected(tmp_path: Path) -> None:
    patterns = sorted(
        (docker_boundary.REQUIRED_SECRET_EXCLUSIONS - {"*.key"})
        | docker_boundary.REQUIRED_REINCLUSIONS
    )
    _write_broad_context(tmp_path, "\n".join(patterns) + "\n")

    findings = docker_boundary.policy_violations(_policy(), repo_root=tmp_path)

    assert len(findings) == 1
    assert "missing required secret exclusion '*.key'" in findings[0]
    assert "frontend/Dockerfile:3" in findings[0]


def test_missing_required_reinclusion_is_rejected(tmp_path: Path) -> None:
    patterns = sorted(docker_boundary.REQUIRED_SECRET_EXCLUSIONS)
    _write_broad_context(tmp_path, "\n".join(patterns) + "\n")

    findings = docker_boundary.policy_violations(_policy(), repo_root=tmp_path)

    assert findings == [
        "frontend/.dockerignore: missing required narrow reinclusion '!.env.example'"
    ]


def test_unreviewed_reinclusion_is_rejected(tmp_path: Path) -> None:
    _write_broad_context(
        tmp_path,
        _complete_ignore_text() + "!.env.production\n",
    )

    findings = docker_boundary.policy_violations(_policy(), repo_root=tmp_path)

    assert findings == [
        "frontend/.dockerignore: unexpected reinclusion '!.env.production'; "
        "explicit policy review is required"
    ]


def test_dockerfile_copy_contract_change_fails_closed(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "Dockerfile").write_text(
        "FROM node:alpine\nCOPY package.json ./\n",
        encoding="utf-8",
    )
    (frontend / ".dockerignore").write_text(
        _complete_ignore_text(),
        encoding="utf-8",
    )

    findings = docker_boundary.policy_violations(_policy(), repo_root=tmp_path)

    assert findings == [
        "frontend/Dockerfile: expected broad Docker context copy is absent; "
        "review this guard with the Dockerfile change"
    ]


def test_broad_copy_with_options_and_comment_is_recognized(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "Dockerfile").write_text(
        "FROM node:alpine\nCOPY --chown=node:node . . # app source\n",
        encoding="utf-8",
    )
    (frontend / ".dockerignore").write_text(
        _complete_ignore_text(),
        encoding="utf-8",
    )

    assert docker_boundary.policy_violations(_policy(), repo_root=tmp_path) == []


def test_ignore_read_failure_does_not_leak_exception_detail(
    tmp_path: Path, monkeypatch,
) -> None:
    _write_broad_context(tmp_path, _complete_ignore_text())
    ignore_file = tmp_path / "frontend" / ".dockerignore"
    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args, **kwargs):
        if self == ignore_file:
            raise PermissionError("sensitive local path detail")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    findings = docker_boundary.policy_violations(_policy(), repo_root=tmp_path)

    assert findings == ["frontend/.dockerignore: read failure: PermissionError"]
    assert "sensitive local path detail" not in findings[0]
