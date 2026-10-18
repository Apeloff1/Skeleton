#!/usr/bin/env bash
# One change-scope implementation for the restored CI/CD workflow (#4109)
# and for Merge Readiness lanes that would otherwise repeat it.
#
# Writes frontend, backend, python, and docker (=true|false) to
# $GITHUB_OUTPUT when Actions sets it, otherwise to stdout.
# Main pushes, dispatches, and CI-policy edits run every lane. A pull
# request is scoped only when the checkout is the merge commit (HEAD^2);
# a shallow non-merge checkout fails closed to "run everything".
set -euo pipefail

out() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf '%s\n' "$1" >> "$GITHUB_OUTPUT"
  else
    printf '%s\n' "$1"
  fi
}

all() {
  local key
  for key in frontend backend python docker; do
    out "$key=true"
  done
}

if [ "${EVENT_NAME:-}" != "pull_request" ] || ! git rev-parse --verify -q HEAD^2 >/dev/null; then
  all
  exit 0
fi

changed="$(git diff --name-only HEAD^1 HEAD)"
if printf '%s\n' "$changed" | grep -Eq '^(\.github/workflows/(ci|merge-readiness)\.yml|\.github/ci/|pyproject\.toml|requirements[^/]*\.txt)'; then
  all
  exit 0
fi

has() {
  if printf '%s\n' "$changed" | grep -Eq "$1"; then
    echo true
  else
    echo false
  fi
}

out "frontend=$(has '^frontend/')"
out "backend=$(has '^backend/')"
out "python=$(has '^(skeleton/|tests/|scripts/|java-accelerators/)')"
out "docker=$(has '(^|/)Dockerfile|^\.dockerignore|compose[^/]*\.ya?ml$')"
