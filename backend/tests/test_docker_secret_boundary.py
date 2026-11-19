from __future__ import annotations

from pathlib import Path

from backend.scripts import check_docker_secret_boundary as docker_boundary

REPO_ROOT = Path(__file__).resolve().parents[2]


def _policy() -> docker_boundary.DockerContextPolicy:
    return docker_boundary.DockerContextPolicy(
        Path("frontend/Dockerfile"), Path("frontend/.dockerignore")
    )


def _complete_ignore_text() -> str:
    return (
        "\n".join(
            sorted(
                docker_boundary.REQUIRED_SECRET_EXCLUSIONS
                | docker_boundary.REQUIRED_REINCLUSIONS
            )
        )
        + "\n"
    )


def _write_broad_context(tmp_path: Path, ignore_text: str | None) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "Dockerfile").write_text(
        "FROM node:alpine\nWORKDIR /app\nCOPY . .\n", encoding="utf-8"
    )
    if ignore_text is not None:
        (frontend / ".dockerignore").write_text(ignore_text, encoding="utf-8")


def _write_dockerfile(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "Dockerfile"
    path.write_text(content, encoding="utf-8")
    return Path("Dockerfile")


def test_current_repository_docker_secret_boundary_is_complete() -> None:
    assert docker_boundary.scan_repository(repo_root=REPO_ROOT) == []


def test_missing_dockerignore_fails_closed(tmp_path: Path) -> None:
    _write_broad_context(tmp_path, None)
    assert docker_boundary.policy_violations(_policy(), repo_root=tmp_path) == [
        "frontend/.dockerignore: read failure: FileNotFoundError"
    ]


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
    _write_broad_context(
        tmp_path,
        "\n".join(sorted(docker_boundary.REQUIRED_SECRET_EXCLUSIONS)) + "\n",
    )
    assert docker_boundary.policy_violations(_policy(), repo_root=tmp_path) == [
        "frontend/.dockerignore: missing required narrow reinclusion '!.env.example'"
    ]


def test_unreviewed_reinclusion_is_rejected(tmp_path: Path) -> None:
    _write_broad_context(tmp_path, _complete_ignore_text() + "!.env.production\n")
    assert docker_boundary.policy_violations(_policy(), repo_root=tmp_path) == [
        "frontend/.dockerignore: unexpected reinclusion '!.env.production'; explicit policy review is required"
    ]


def test_dockerfile_copy_contract_change_fails_closed(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "Dockerfile").write_text(
        "FROM node:alpine\nCOPY package.json ./\n", encoding="utf-8"
    )
    (frontend / ".dockerignore").write_text(_complete_ignore_text(), encoding="utf-8")
    assert docker_boundary.policy_violations(_policy(), repo_root=tmp_path) == [
        "frontend/Dockerfile: expected broad Docker context copy is absent; review this guard with the Dockerfile change"
    ]


def test_broad_copy_with_options_and_comment_is_recognized(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "Dockerfile").write_text(
        "FROM node:alpine\nCOPY --chown=node:node . . # app source\n",
        encoding="utf-8",
    )
    (frontend / ".dockerignore").write_text(_complete_ignore_text(), encoding="utf-8")
    assert docker_boundary.policy_violations(_policy(), repo_root=tmp_path) == []


def test_ignore_read_failure_does_not_leak_exception_detail(
    tmp_path: Path, monkeypatch
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


def test_root_context_requires_recursive_env_exclusions() -> None:
    root_policy = docker_boundary.POLICIES[1]
    assert "**/.env" in root_policy.required_exclusions
    assert "**/.env.*" in root_policy.required_exclusions
    assert "!**/.env.example" in root_policy.required_reinclusions
    assert docker_boundary.policy_violations(root_policy, repo_root=REPO_ROOT) == []


def test_secret_bearing_build_arg_is_forbidden(tmp_path: Path) -> None:
    dockerfile = _write_dockerfile(
        tmp_path,
        "FROM python:alpine\nARG OPENAI_API_KEY\nRUN echo safe\n",
    )
    findings = docker_boundary.dockerfile_secret_directive_violations(
        dockerfile, repo_root=tmp_path
    )
    assert len(findings) == 1
    assert "OPENAI_API_KEY" in findings[0]
    assert "Docker ARG/ENV" in findings[0]


def test_secret_bearing_baked_env_is_forbidden_without_echoing_value(
    tmp_path: Path,
) -> None:
    secret_value = "do-not-echo-this-value"
    dockerfile = _write_dockerfile(
        tmp_path,
        f"FROM python:alpine\nENV JWT_SECRET={secret_value} SAFE_MODE=1\n",
    )
    findings = docker_boundary.dockerfile_secret_directive_violations(
        dockerfile, repo_root=tmp_path
    )
    assert len(findings) == 1
    assert "JWT_SECRET" in findings[0]
    assert secret_value not in findings[0]


def test_backtick_escape_continuation_cannot_hide_secret_env(tmp_path: Path) -> None:
    secret_value = "do-not-echo-backtick-secret"
    dockerfile = _write_dockerfile(
        tmp_path,
        "# escape=`\n"
        "FROM python:alpine\n"
        "ENV SAFE_MODE=1 `\n"
        f"    JWT_SECRET={secret_value}\n",
    )
    findings = docker_boundary.dockerfile_secret_directive_violations(
        dockerfile, repo_root=tmp_path
    )
    assert len(findings) == 1
    assert "JWT_SECRET" in findings[0]
    assert secret_value not in findings[0]


def test_safe_image_arg_and_nonsecret_env_are_allowed(tmp_path: Path) -> None:
    dockerfile = _write_dockerfile(
        tmp_path,
        "ARG PYTHON_IMAGE=python:3.14-alpine\n"
        "FROM ${PYTHON_IMAGE}\n"
        "ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1\n",
    )
    assert (
        docker_boundary.dockerfile_secret_directive_violations(
            dockerfile, repo_root=tmp_path
        )
        == []
    )


def test_buildkit_secret_mount_is_the_allowed_build_time_secret_channel(
    tmp_path: Path,
) -> None:
    dockerfile = _write_dockerfile(
        tmp_path,
        "FROM python:alpine\n"
        "RUN --mount=type=secret,id=pypi_token python -m build\n",
    )
    assert (
        docker_boundary.dockerfile_secret_directive_violations(
            dockerfile, repo_root=tmp_path
        )
        == []
    )


def test_malformed_secret_directive_fails_closed_without_payload(tmp_path: Path) -> None:
    dockerfile = _write_dockerfile(
        tmp_path,
        'FROM python:alpine\nENV "unterminated\n',
    )
    findings = docker_boundary.dockerfile_secret_directive_violations(
        dockerfile, repo_root=tmp_path
    )
    assert findings == ["Dockerfile:2: malformed ENV instruction"]
    assert "unterminated" not in findings[0]


def test_docker_secret_workflow_tracks_every_deployable_context() -> None:
    workflow = (
        REPO_ROOT / ".github" / "workflows" / "docker-secret-boundary.yml"
    ).read_text(encoding="utf-8")
    for path in (
        "Dockerfile",
        "backend/Dockerfile",
        ".dockerignore",
        "frontend/Dockerfile",
        "frontend/.dockerignore",
    ):
        assert f"- '{path}'" in workflow
