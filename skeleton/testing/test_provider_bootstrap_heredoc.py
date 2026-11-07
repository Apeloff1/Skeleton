"""Provider Dockerfile materialization must not interpret heredoc program text as stages."""
from scripts.check_provider_bootstrap import _docker_materialization_stages


def test_python_from_inside_heredoc_is_not_a_docker_from_stage():
    docker = (
        "FROM python:3.14 AS production\n"
        "WORKDIR /app\n"
        "RUN python - <<'PY'\n"
        "from glob import glob\n"
        "print('FROM untrusted AS fake')\n"
        "PY\n"
        "COPY --chown=appuser:appuser . .\n"
        "FROM production AS development\n"
    )
    instructions, stages = _docker_materialization_stages(docker)
    assert [stage["name"] for stage in stages] == ["production", "development"]
    assert ("COPY --chown=appuser:appuser . .", "/app") in stages[-1]["copies"]
    assert all("from glob import glob" not in instruction for instruction in instructions)


def test_unterminated_heredoc_fails_closed_on_stage_materialization():
    instructions, stages = _docker_materialization_stages(
        "FROM python:3.14 AS production\nRUN python - <<'PY'\nfrom glob import glob\n"
    )
    assert instructions
    assert stages == []
