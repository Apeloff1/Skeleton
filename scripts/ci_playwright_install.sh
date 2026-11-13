#!/usr/bin/env bash
# Install the pinned Playwright browser without changing the project lockfile.
# APT mirror DNS failures are transient on hosted runners; retry the complete
# browser/dependency install, never treat an unsuccessful attempt as success.
set -euo pipefail

if [[ ! "${PLAYWRIGHT_VERSION:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Playwright install: invalid or missing pinned version" >&2
  exit 2
fi

npm install --no-save --no-package-lock --no-audit --no-fund --ignore-scripts \
  "@playwright/test@${PLAYWRIGHT_VERSION}"

for attempt in 1 2 3; do
  if npx --no-install playwright install --with-deps chromium; then
    echo "Playwright browser and system dependencies installed (attempt ${attempt})"
    exit 0
  fi
  if (( attempt == 3 )); then
    echo "Playwright install: all 3 dependency-install attempts failed" >&2
    exit 1
  fi
  # Avoid hammering a temporarily unavailable APT mirror. No fallbacks that
  # omit system dependencies or substitute an unpinned browser are permitted.
  sleep "$((attempt * 15))"
done
