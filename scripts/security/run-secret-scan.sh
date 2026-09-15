#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXPECTED_GITLEAKS_VERSION="8.24.3"
cd "$ROOT_DIR"

printf '%s\n' '[secret-scan] running repository-native high-confidence scanner'
python backend/scripts/check_secret_hygiene.py

if ! command -v gitleaks >/dev/null 2>&1; then
  cat >&2 <<EOF
[secret-scan] gitleaks is required for full-history scanning.
Install gitleaks ${EXPECTED_GITLEAKS_VERSION}, then rerun:
  bash scripts/security/run-secret-scan.sh
EOF
  exit 2
fi

installed_version="$(gitleaks version 2>/dev/null | tr -d '[:space:]')"
if [[ "$installed_version" != *"${EXPECTED_GITLEAKS_VERSION}"* ]]; then
  printf '%s\n' \
    "[secret-scan] warning: CI pins gitleaks ${EXPECTED_GITLEAKS_VERSION}; local version is ${installed_version:-unknown}" \
    >&2
fi

printf '%s\n' '[secret-scan] scanning Git history with Gitleaks (findings redacted)'
gitleaks git --config=.gitleaks.toml --redact=100 --no-banner .

printf '%s\n' '[secret-scan] passed'
