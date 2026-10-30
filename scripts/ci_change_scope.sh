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

# Consume the entire NUL-delimited Git diff. This is bounded in memory,
# handles arbitrary legal filenames, and propagates producer errors via pipefail.
# Never exit a grep early: that would SIGPIPE the diff producer on large PRs.
git diff --name-only -z HEAD^1 HEAD | {
  seen=false
  force_all=false
  frontend=false
  backend=false
  python=false
  docker=false

  while IFS= read -r -d '' path; do
    seen=true
    case "$path" in
      .github/workflows/ci.yml|.github/workflows/merge-readiness.yml|.github/ci/*|pyproject.toml|requirements*.txt)
        force_all=true
        ;;
    esac
    case "$path" in frontend/*) frontend=true ;; esac
    case "$path" in backend/*) backend=true ;; esac
    case "$path" in skeleton/*|tests/*|scripts/*|java-accelerators/*) python=true ;; esac
    case "$path" in
      Dockerfile*|*/Dockerfile*|.dockerignore|compose*.yml|compose*.yaml|frontend/nginx.conf|frontend/scripts/test-nginx-runtime-dns.mjs)
        docker=true
        ;;
    esac
  done

  if [ "$seen" = false ] || [ "$force_all" = true ]; then
    all
  else
    out "frontend=$frontend"
    out "backend=$backend"
    out "python=$python"
    out "docker=$docker"
  fi
}
