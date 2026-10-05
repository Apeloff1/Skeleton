#!/usr/bin/env bash
# clean-stray-files.sh — guard against the EAS tarball corruption that broke
# Android builds ("ENOENT: no such file or directory, lstat '<garbage-name>'").
#
# Wipes stray, accidental, 0-byte files in the frontend root whose names are
# either non-ASCII/control-char garbage or known command-word artifacts
# (Add, Run, Verify, …) that occasionally get created by broken heredocs/echos.
# Real project files are never 0-byte at the repo root, so this is safe.
#
# Run manually any time, or it runs automatically before `yarn start` (prestart).
set -euo pipefail
cd "$(dirname "$0")/.."

removed=0

# 1) Any 0-byte file at the repo root with a NON-ASCII or control char in its name.
while IFS= read -r -d '' f; do
  rm -f -- "$f" && removed=$((removed+1)) && echo "  ✗ removed corrupted-name file: $(printf %q "$f")"
done < <(find . -maxdepth 1 -type f -size 0 -name '*[![:print:]]*' -print0 2>/dev/null || true)

# 2) Known stray command-word 0-byte files at the repo root.
for name in Add Ensure Expand Verify Import Run Write Update Create Remove Delete Fix; do
  if [ -f "./$name" ] && [ ! -s "./$name" ]; then
    rm -f -- "./$name" && removed=$((removed+1)) && echo "  ✗ removed stray file: $name"
  fi
done

if [ "$removed" -eq 0 ]; then
  echo "✓ clean-stray-files: nothing to clean (frontend root is tar-safe)."
else
  echo "✓ clean-stray-files: removed $removed stray file(s) — EAS tarball is safe."
fi
