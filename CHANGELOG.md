# CHANGELOG

All notable changes to Skeleton.

---

## 2026-09-04 — Operator diagnostics command surface

- Added direct diagnostics surfaces for failures, repairs, activity, and recurring issues/targets.
- Added failure/activity/recurring cards and wired them through the command deck and HTTP.
- Updated corrective-control docs and freeze docs to reflect parity across game logic and direct operator diagnostics.
- Version 2026.09.04-diagnostics.

---

## 2026-09-04 — Corrective-control segment docs + freeze

- Added `docs/CORRECTIVE_CONTROL_SEGMENT.md` describing the quality/repair control plane.
- Updated `docs/STATUS.md`, `docs/BACKLOG.md`, and `BUILD_PLAN.md` to reflect the corrective-control lineage.
- Marks game-logic repair parity and operator repair commands as the clearest next open work.
- Version 2026.09.04-corrective-docs.

---

## 2026-09-03 — Bound ledger stores CDX handles; X lab pointers

- bind_row writes cdx + xarchive. observe records field_pct/cdx_n.
- Six X house pointers. Walk n=4 houses Xarchive/IA/X/GitHub, cdx_n=4.
- Version 2026.09.03-cdxled.
