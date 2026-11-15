# GameForge source and route coverage evidence

The old Mission Control panel treated six historical archive inventories as
100% implemented, even when runtime activation was disabled. It also sent
loopback HTTP requests without caller identity and equated any HTTP 200 with
production readiness.

The replacement statically parses bounded Python source, records file hashes,
declaration names and scanner failures, and emits a deterministic source
manifest. It does not execute discovered modules, follow source symlinks or
make network calls. Route registration is inspected from the existing ASGI
application without invoking handlers. An unavailable or partial inventory is
reported explicitly. The cache is process-local and refreshes after 60 seconds;
its digest is an inventory receipt, not a signed release attestation.

Historical archive counts are retained without inferred completion. To claim
archive parity, recover the original archive bytes and map each manifest entry
to reviewed current source and behavior tests. Live readiness additionally
requires exact-head integration and independent native/device qualification.

Focused validation:
    cd backend && python -m pytest -q tests/test_gameforge_coverage_security.py tests/test_chronological_gameforge_coverage.py
    cd frontend && yarn typecheck

Static source inspection assumes an operator-owned installation tree. File
identity is rechecked around each bounded read; it is not a hostile filesystem
sandbox. No native process is launched.
