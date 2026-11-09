from __future__ import annotations

import base64
import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
DISPATCH = REPO_ROOT / ".emergent" / "cron" / "dispatch_webhook.sh"


def _fake_curl(tmp_path: Path) -> Path:
    fake = tmp_path / "curl"
    fake.write_text(
        "#!/bin/sh\n"
        ": \"${FAKE_CURL_LOG:?}\"\n"
        "printf '%s\\n' \"$@\" > \"$FAKE_CURL_LOG\"\n"
        "printf '204'\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake


def _run_dispatch(
    tmp_path: Path,
    *,
    endpoint: str = "https://preview.example.test/webhook",
    method: str = "POST",
    secret: str | None = "cron-secret",
) -> tuple[subprocess.CompletedProcess[str], Path]:
    _fake_curl(tmp_path)
    env_file = tmp_path / ".env"
    if secret is None:
        env_file.write_text("", encoding="utf-8")
    else:
        env_file.write_text(f"WEBHOOK_CRON_SECRET={secret}\n", encoding="utf-8")

    curl_log = tmp_path / "curl-args.txt"
    env = os.environ.copy()
    env.update(
        {
            "AT_DATE": "",
            "CRON_NAME": "nightly-security-check",
            "END_DATE": "",
            "ENDPOINT_URL_B64": base64.b64encode(endpoint.encode()).decode(),
            "FAKE_CURL_LOG": str(curl_log),
            "JOB_ID": "job-123",
            "METHOD": method,
            "PATH": f"{tmp_path}:{env.get('PATH', '')}",
            "WEBHOOK_ENV_FILE": str(env_file),
        }
    )

    result = subprocess.run(
        ["/bin/sh", str(DISPATCH)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, curl_log


def test_dispatch_never_forwards_bearer_across_host_redirects(tmp_path: Path) -> None:
    result, curl_log = _run_dispatch(tmp_path)

    assert result.returncode == 0, result.stderr
    args = curl_log.read_text(encoding="utf-8").splitlines()
    assert "--location-trusted" not in args
    assert "--location" in args
    assert "Authorization: Bearer cron-secret" in args

    proto_index = args.index("--proto")
    proto_redir_index = args.index("--proto-redir")
    assert args[proto_index + 1] == "=https"
    assert args[proto_redir_index + 1] == "=https"


def test_dispatch_rejects_non_https_endpoint_before_curl(tmp_path: Path) -> None:
    result, curl_log = _run_dispatch(
        tmp_path,
        endpoint="http://preview.example.test/webhook",
    )

    assert result.returncode == 64
    assert "must use https" in result.stderr
    assert not curl_log.exists()


def test_dispatch_rejects_connect_method_before_curl(tmp_path: Path) -> None:
    result, curl_log = _run_dispatch(tmp_path, method="CONNECT")

    assert result.returncode == 64
    assert "unsupported HTTP method" in result.stderr
    assert not curl_log.exists()


def test_dispatch_fails_closed_when_secret_is_missing(tmp_path: Path) -> None:
    result, curl_log = _run_dispatch(tmp_path, secret=None)

    assert result.returncode == 78
    assert "WEBHOOK_CRON_SECRET is missing" in result.stderr
    assert not curl_log.exists()
