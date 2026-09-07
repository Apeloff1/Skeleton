#!/usr/bin/env bash
# Skeleton CI pipeline — run locally or in any CI runner.
# Usage: ./scripts/ci.sh
set -euo pipefail

echo "==> Compile check"
python -m compileall skeleton -q

echo "==> Import smoke check"
python -c "import skeleton; print('skeleton', skeleton.__version__)"
python -c "from skeleton.genesis import Genesis; g = Genesis(seed=42).boot(); print('handles:', len(g.handles))"

echo "==> Forge verification"
bash scripts/verify-forge.sh

echo "==> Cockpit smoke"
bash scripts/cockpit-smoke.sh

echo "==> Test suite"
if command -v pytest >/dev/null 2>&1; then
  python -m pytest skeleton/testing -v --tb=short
else
  python -m unittest discover skeleton/testing -v
fi

echo "==> CI passed"
