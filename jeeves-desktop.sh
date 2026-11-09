#!/usr/bin/env sh
# Local-only Jeeves workbench entry point. No installer/network/provider fallback.
set -eu
cd -- "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec python3 -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_app "$@"
