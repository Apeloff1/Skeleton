import base64
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DISPATCH_SCRIPT = REPO_ROOT / ".emergent" / "cron" / "dispatch_webhook.sh"


def _run_dispatch(tmp_path: Path, redirect_url: str, endpoint: str = "https://preview.example/hook"):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log_path = tmp_path / "curl.log"
    env_path = tmp_path / ".env"
    env_path.write_text("WEBHOOK_CRON_SECRET=top-secret-token\n", encoding="utf-8")

    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        """#!/bin/sh
set -eu
last=""
for arg in "$@"; do
    last="$arg"
done
printf '%s\t%s\n' "$last" "$*" >> "$FAKE_CURL_LOG"
case "$last" in
    https://preview.example/hook)
        printf '307\n%s\n' "$FAKE_REDIRECT_URL"
        ;;
    https://internal.preview.example/hook)
        printf '200\n\n'
        ;;
    *)
        printf '200\n\n'
        ;;
esac
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
            "CRON_NAME": "security-test",
            "METHOD": "POST",
            "ENDPOINT_URL_B64": base64.b64encode(endpoint.encode()).decode(),
            "WEBHOOK_ENV_FILE": str(env_path),
            "FAKE_CURL_LOG": str(log_path),
            "FAKE_REDIRECT_URL": redirect_url,
        }
    )
    result = subprocess.run(
        ["sh", str(DISPATCH_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    return result, log


def test_dispatch_does_not_forward_secret_to_arbitrary_redirect(tmp_path: Path) -> None:
    result, log = _run_dispatch(tmp_path, "https://evil.example/steal")

    assert "http=000" in result.stdout
    assert "https://preview.example/hook" in log
    assert "https://evil.example/steal" not in log
    assert log.count("top-secret-token") == 1


def test_dispatch_allows_expected_internal_preview_redirect(tmp_path: Path) -> None:
    result, log = _run_dispatch(tmp_path, "https://internal.preview.example/hook")

    assert "http=200" in result.stdout
    assert "https://preview.example/hook" in log
    assert "https://internal.preview.example/hook" in log
    assert log.count("top-secret-token") == 2


def test_dispatch_rejects_non_https_origin_before_sending_secret(tmp_path: Path) -> None:
    result, log = _run_dispatch(
        tmp_path,
        "https://internal.preview.example/hook",
        endpoint="http://preview.example/hook",
    )

    assert "reason=invalid_endpoint" in result.stdout
    assert log == ""


def test_dispatch_never_uses_curl_location_trusted() -> None:
    script = DISPATCH_SCRIPT.read_text(encoding="utf-8")
    assert "--location-trusted" not in script
