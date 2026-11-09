# Session 28 — Forge quality-gate polish pass

## Done
- **New module** `backend/routes/quality_polish.py`: `polish_pass(kind, content)` — targeted
  rewrite loop against the 95 gate. Feeds the auditor's feedback + 3 weakest factors into an
  editor-style rewrite (NOT a fresh re-roll), re-audits each pass, keeps the best artifact,
  stops at MAX_POLISH_PASSES=5 or after 2 non-improving passes (plateau guard). Never raises;
  always returns best content + per-pass trail (`passes[]`, `improved_by`, `passed`).
- **Endpoints** mounted on the already-registered Sentinel router (`quality_control.py`):
  - `POST /api/quality-control/polish/{kind}?simulate=` — one artifact against the gate.
  - `POST /api/quality-control/polish-batch` — up to 8 artifacts, sequential, summary counts.
- PR: https://github.com/Apeloff1/Skeleton/pull/1 (draft), branch `backend/quality-polish`.

## Why the endpoints live in quality_control.py
`core/routes_registry.py` is ~23 KB — too large to round-trip safely through the contents API
(truncation risk). `quality_control.py` is the quality-owned, already-registered router, so the
endpoints were appended there. If the registry is ever edited locally, move them into a
self-prefixed `routes/quality_polish_api.py` and add one line to KNOWN_ROUTES.

## Not yet done (next fork)
- Wire `polish_pass` into `_llm_json`'s retry path in `routes/game_kb.py` so every forge gets
  the loop automatically (use `simulate=True` for physics/tileset/cinematic/camera/procedural).
- Deferred forge stages from NEXT_FORK (quality, fine-tuning, bestiary, nature, realism,
  fine-mechanic, movement, city) — build after this lands.
- curl-verify both endpoints against a live deploy (no live env available this session).
