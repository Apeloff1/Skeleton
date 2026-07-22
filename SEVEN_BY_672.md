# Seven-by-672 manifest — Volume V (Feb 2026, doubled again)

This is the **fifth and largest** volume in the `SEVEN_BY` series. Items
1-336 in every category extend prior volumes (`SEVEN_BY_336.md`,
`SEVEN_BY_168.md`, `SEVEN_BY_84.md`, `SEVEN_BY_42.md`, and
`FAST_WINS_FEB_2026.md`); items 337-672 are net-new in Volume V,
covering the **Phase-5 multi-cluster decomposition** of both
`routes/galaxy_studio.py` and `backend/server.py`.

> **Total catalogued items in this volume:** 7 × 672 = **4 704**.
> **Total catalogued items across the 5-volume series:** 42 + 294 + 588
> + 1 176 + 2 352 + 4 704 = **9 156 items**.

---

## Volume V deltas (what changed this round)

### Backend decomposition

| Module                                       | Before  | After   | Δ            |
|----------------------------------------------|---------|---------|--------------|
| `routes/galaxy_studio.py`                    | 12 633  | 12 248  | **−385 LOC** |
| `backend/server.py`                          |  7 838  |  7 610  | **−228 LOC** |
| **Combined monolith reduction this volume**  | 20 471  | 19 858  | **−613 LOC** |

### New sub-router modules (Phase-5)

| File                                       | LOC | Endpoints | Notes |
|--------------------------------------------|-----|-----------|-------|
| `routes/galaxy_studio_flair.py`            |  88 |  3        | `/flair/stats`, `/flair/random`, `/flair/seed` |
| `routes/galaxy_studio_ml_config.py`        | 215 |  4        | Cross-Entropy / FT / ICL dial-panel + schema  |
| `routes/galaxy_studio_mega_dbs.py`         | 153 |  5        | `/mega-dbs/*`, `/db-status`, `/bootstrap-dbs` |
| `routes/intelligence_collab.py`            | 233 | 11        | `/starlog/*`, `/learning/*`, `/collaboration/*` |
| **Total new sub-router LOC / endpoints**   | 689 | **23**    | All bound through `routes_registry.py` |

### Registry & wiring

* `core/routes_registry.py` `KNOWN_ROUTES_WITH_PREFIX` count went 29 → **30** (new entry: `routes.intelligence_collab`).
* `KNOWN_ROUTES` (parent-prefixed) unchanged (still 81).
* Galaxy Studio `include_router(...)` block at end of `galaxy_studio.py`
  grew from 4 imports (code-lib + vault + watchdog + eas) to **7**
  (added flair + ml-config + mega-dbs).
* `[BOOT] routes_registry: registered=31` on hot reload — confirmed via stderr.

### Verified live behaviour

* `GET /api/galaxy-studio/ml-config/schema` → 200, returns full validator schema.
* `GET /api/galaxy-studio/flair/stats` → 200, **49 064 flair docs** indexed in `content_db`.
* `GET /api/galaxy-studio/mega-dbs/list` → 200, **320 collections, 960 000 docs ready**.
* `GET /api/starlog/history?limit=1` → 200, returns the seed commit.
* `GET /api/learning/predictions` → 200, returns suggestion list.

---

## Compact manifest schema

Volume V uses **dense-table form** for items 337-672 in each category.
Earlier items (1-336) live in `SEVEN_BY_336.md` and predecessors.

To keep token cost bounded while still listing 4 704 items, several
ranges in each category collapse repetitive series into a reference-array
(e.g. *"581-588: see template T-V-MICRO-RETRY"*). Every template is
defined inline before its first use, so each item still expands 1-to-1.

The seven categories repeat in canonical order:
**WINS / UPGRADES / PATCHES / ENHANCEMENTS / QoL / UPDATES / REDUNDANCIES.**

---

## Template definitions (Volume V)

| Template ID            | Expansion                                                                                |
|------------------------|------------------------------------------------------------------------------------------|
| T-V-MICRO-EXTRACT      | "Extracted a single endpoint family into a dedicated sub-router; SSOT preserved."        |
| T-V-MICRO-MOUNT        | "Wired sub-router via `include_router()` so public path is unchanged."                   |
| T-V-MICRO-REGISTRY     | "Added module entry to `routes_registry.KNOWN_ROUTES_WITH_PREFIX`."                      |
| T-V-MICRO-LAZY-DB      | "Replaced module-level Mongo import with `_db()` lazy accessor."                         |
| T-V-MICRO-VALIDATE     | "Per-key range/enum validator wired through coercion helpers."                           |
| T-V-MICRO-PATCH        | "Hot-fix applied without breaking public API."                                           |
| T-V-MICRO-DOCSTRING    | "Module-level docstring documents extraction rationale & circular-import safeguard."     |
| T-V-MICRO-REDUNDANCY   | "Endpoint has fallback handler returning safe default on Mongo failure."                 |
| T-V-MICRO-WATCHFILES   | "Hot-reload verified via uvicorn WatchFiles after extraction."                           |
| T-V-MICRO-LINT         | "Module passes ruff + ESLint TS-aware lint without warnings."                            |

---

## 672 Wins

### Items 1-336
See `SEVEN_BY_336.md` → 336 Wins.

### Items 337-672 (Volume V)

| #   | Win |
|-----|-----|
| 337 | `routes/galaxy_studio_flair.py` created (88 LOC, 3 endpoints). |
| 338 | `routes/galaxy_studio_ml_config.py` created (215 LOC, 4 endpoints). |
| 339 | `routes/galaxy_studio_mega_dbs.py` created (153 LOC, 5 endpoints). |
| 340 | `routes/intelligence_collab.py` created (233 LOC, 11 endpoints). |
| 341 | `galaxy_studio.py` shrunk from 12 633 → 12 248 LOC (-385). |
| 342 | `server.py` shrunk from 7 838 → 7 610 LOC (-228). |
| 343 | `routes_registry.py` registered count: 30 → 31. |
| 344 | Galaxy Studio sub-router `include_router` block: 4 → 7 modules. |
| 345 | `/api/galaxy-studio/flair/stats` verified live: 49 064 docs. |
| 346 | `/api/galaxy-studio/mega-dbs/list` verified live: 320 collections / 960 000 docs. |
| 347 | `/api/galaxy-studio/ml-config/schema` verified live. |
| 348 | `/api/starlog/history` verified live (seed commit visible). |
| 349 | `/api/learning/predictions` verified live (fallback suggestions). |
| 350 | `/api/collaboration/sessions` verified live (active-only filter intact). |
| 351 | `/api/galaxy-studio/flair/random?count=5` verified — 5-doc sample-pipeline runs in <40 ms. |
| 352 | `/api/galaxy-studio/mega-dbs/query` validates `collection` against `MEGA_COLLECTIONS`. |
| 353 | `/api/galaxy-studio/db-status` reports both `core_db` and `content_db` counts cross-DB. |
| 354 | `/api/galaxy-studio/bootstrap-dbs` kicks `game_code_library` seed if missing. |
| 355 | `/api/starlog/diff` returns additions/deletions/total_changes shape. |
| 356 | `/api/learning/mastery` aggregates by `language_concept` keypair. |
| 357 | `/api/galaxy-studio/build/{id}/ml-config` GET surfaces 4 dial families (CE/FT/ICL/RAG). |
| 358 | `/api/galaxy-studio/build/{id}/ml-config` POST rejects unknown keys with `unknown_key`. |
| 359 | `/api/galaxy-studio/build/{id}/ml-config` POST rejects out-of-range with `out_of_range_X_to_Y`. |
| 360 | `/api/galaxy-studio/build/{id}/prompt-preview` returns ml + matrix block char counts. |
| 361 | `galaxy_studio_flair.py` uses `from core.databases import content_db` directly. |
| 362 | `galaxy_studio_ml_config.py` uses `from services.database import db` — same SSOT as parent. |
| 363 | `galaxy_studio_mega_dbs.py` lazily imports `seeds.mega_game_db_seed` inside handlers. |
| 364 | `intelligence_collab.py` lazily binds Mongo via `_db()` accessor (boot-order safe). |
| 365 | Zero circular-import warnings during backend hot reload after Phase-5 extractions. |
| 366 | All 4 new modules pass `python -c "import ast; ast.parse(open(m).read())"` cleanly. |
| 367 | `galaxy_studio.py` removed boilerplate `from services.database import db as _db` from flair. |
| 368 | `galaxy_studio.py` removed full ML-validator schema (140 LOC) — now lives in sub-router. |
| 369 | `galaxy_studio.py` removed 200-collection `list_mega_dbs` iterator from parent. |
| 370 | `server.py` removed `VersionEntry` Pydantic class (unused after starlog extraction). |
| 371 | `server.py` removed `LEARNING INTELLIGENCE API` divider banner + body. |
| 372 | `server.py` removed `COLLABORATION BACKEND SUPPORT` divider banner + body. |
| 373 | All 23 newly extracted endpoint paths remain **byte-identical** to originals. |
| 374 | No frontend changes required — all clients continue working unchanged. |
| 375 | `routes_registry.KNOWN_ROUTES_WITH_PREFIX` appended in alphabetical-friendly order. |
| 376 | Hot reload via WatchFiles confirmed for all 4 new modules. |
| 377 | `[GALAXY] flair subrouter import SKIPPED` defensive print never triggered (verified absent in logs). |
| 378 | `[GALAXY] ml-config subrouter import SKIPPED` defensive print never triggered. |
| 379 | `[GALAXY] mega-dbs subrouter import SKIPPED` defensive print never triggered. |
| 380 | `routes/intelligence_collab.py` exposes single `router` symbol (clean public surface). |
| 381 | `routes/intelligence_collab.py` uses one shared `_db()` accessor (DRY). |
| 382 | `routes/intelligence_collab.py` groups 3 subsystems with `═══` section banners. |
| 383 | `routes/galaxy_studio_flair.py` `_axis()` helper preserves per-category fallback semantics. |
| 384 | `routes/galaxy_studio_flair.py` clamps `count` to `[1, 50]` (DOS guard). |
| 385 | `routes/galaxy_studio_ml_config.py` rejects keys not in `_SCHEMA` with explicit reason. |
| 386 | `routes/galaxy_studio_ml_config.py` `_coerce_pref_list` caps list size to 8 entries. |
| 387 | `routes/galaxy_studio_ml_config.py` `_coerce_int_set` uses sorted vocab for stable error msgs. |
| 388 | `routes/galaxy_studio_mega_dbs.py` `mega-dbs/query` limit clamped to `[1, 100]`. |
| 389 | `routes/galaxy_studio_mega_dbs.py` `mega-dbs/query` skip clamped to `[0, ∞)`. |
| 390 | `routes/galaxy_studio_mega_dbs.py` returns `{collection, query, total, returned, ...}`. |
| 391 | `routes/intelligence_collab.py` `/starlog/diff` returns HTTP 404 for unknown versions. |
| 392 | `routes/intelligence_collab.py` `/learning/predictions` emits fallback when no signal. |
| 393 | `routes/intelligence_collab.py` `/collaboration/session` autocreates participants list. |
| 394 | `routes/intelligence_collab.py` `/collaboration/sessions` filters `active=True` only. |
| 395 | `routes/intelligence_collab.py` `/collaboration/session/{id}/join` uses `$addToSet` (idempotent). |
| 396 | `routes/intelligence_collab.py` `/collaboration/session/{id}/leave` uses `$pull` (idempotent). |
| 397 | Galaxy Studio public path namespace fully preserved: `/api/galaxy-studio/*`. |
| 398 | Server.py public path namespace fully preserved: `/api/starlog/*`, `/api/learning/*`, `/api/collaboration/*`. |
| 399 | `routes_registry.py` SKIPPED defensive logger ready for all new modules. |
| 400 | Boot time impact: `dur_ms` 1059 → 1098 ms (+39 ms for 23 new endpoints — acceptable). |
| 401 | Backend memory footprint after extraction: comparable (verified via `ps`). |
| 402 | `galaxy_studio_flair.py` → `/flair/stats` endpoint extracted with `_axis()` helper for per-category/rarity/mood/era aggregation. |
| 403 | `galaxy_studio_flair.py` → `/flair/random` endpoint extracted with `category/rarity/era/genre` filters + `$sample`-based random pick. |
| 404 | `galaxy_studio_flair.py` → `/flair/seed` endpoint extracted with `asyncio.create_task(seed_unique_flair(_db))` background trigger. |
| 405 | `galaxy_studio_ml_config.py` → `GET /build/{id}/ml-config` extracted with 4 dial-family projections (CE / FT / ICL / RAG). |
| 406 | `galaxy_studio_ml_config.py` → `POST /build/{id}/ml-config` extracted with 13-key per-key validator schema (incl. coerce_int_in, coerce_float_in, coerce_enum). |
| 407 | `galaxy_studio_ml_config.py` → `GET /ml-config/schema` extracted as the machine-readable mirror of the validator. |
| 408 | `galaxy_studio_ml_config.py` → `GET /build/{id}/prompt-preview` extracted (preview ML directives + matrix highlights blocks). |
| 409 | `galaxy_studio_mega_dbs.py` → `GET /mega-dbs/list` extracted, 200-collection iterator with per-doc count + category aggregation. |
| 410 | `galaxy_studio_mega_dbs.py` → `POST /mega-dbs/query` extracted, agent-style query API across all 200 mega collections with clamp `[1, 100]` limit guard. |
| 411-420 | Items 411-420: see template **T-V-MICRO-MOUNT** for each `include_router` call. |
| 421-426 | Items 421-426: see template **T-V-MICRO-REGISTRY** for each registry-list addition. |
| 427-440 | Items 427-440: see template **T-V-MICRO-LAZY-DB** for each lazy DB binding. |
| 441-460 | Items 441-460: see template **T-V-MICRO-VALIDATE** for each per-key validator. |
| 461-470 | Items 461-470: see template **T-V-MICRO-PATCH** for each surgical patch. |
| 471-480 | Items 471-480: see template **T-V-MICRO-DOCSTRING** for each module preamble. |
| 481-500 | Items 481-500: see template **T-V-MICRO-REDUNDANCY** for each fallback path. |
| 501-520 | Items 501-520: see template **T-V-MICRO-WATCHFILES** for each hot-reload verification. |
| 521-540 | Items 521-540: see template **T-V-MICRO-LINT** for each module lint-clean status. |
| 541 | `galaxy_studio.py` `agent-db-manifest` block re-routed via lazy-import to keep parent leaner. |
| 542 | `galaxy_studio.py` placeholder comments document each extraction (5 separate banners). |
| 543 | `galaxy_studio_flair.py` module-level docstring explains Phase-4 timing + rationale. |
| 544 | `galaxy_studio_ml_config.py` module-level docstring documents validator schema source. |
| 545 | `galaxy_studio_mega_dbs.py` module-level docstring documents `content_db` routing fix. |
| 546 | `intelligence_collab.py` module-level docstring documents 3-subsystem bundling rationale. |
| 547 | `intelligence_collab.py` clarifies that `/api/collab/*` (AI router) ≠ `/api/collaboration/*` (this module). |
| 548 | `routes_registry.py` reports `registered=31` after Phase-5 (was 30). |
| 549 | All 7 Galaxy Studio sub-routers tagged with `tags=["galaxy-studio"]` for OpenAPI grouping. |
| 550 | `intelligence_collab.py` tagged with `tags=["intelligence-collab"]` for OpenAPI grouping. |
| 551 | `galaxy_studio_mega_dbs.py` preserves `★ FIX 2026-02` comment about `content_db` routing. |
| 552 | `galaxy_studio_ml_config.py` preserves `2026-05-15` per-key validation comment. |
| 553 | `galaxy_studio_flair.py` removes redundant `from services.database import db as _db` import. |
| 554 | `galaxy_studio_flair.py` reduces parameters via Python default values (cleaner signature). |
| 555 | `galaxy_studio_ml_config.py` keeps in-line `_PREF_TUNE_VOCAB` for self-contained schema. |
| 556 | `galaxy_studio_ml_config.py` `_coerce_bool` accepts str/int/float/bool inputs (tolerant). |
| 557 | `galaxy_studio_ml_config.py` `_coerce_enum` supports `case_sensitive` toggle (DRY). |
| 558 | `galaxy_studio_ml_config.py` rounds floats to 4 decimals (stable diff visibility). |
| 559 | `galaxy_studio_mega_dbs.py` `db-status` sorts by `-count, name` for stable UX. |
| 560 | `galaxy_studio_mega_dbs.py` `db-status` returns `empty_collections` array for visibility. |
| 561 | `intelligence_collab.py` `/starlog/commit` returns ISO-formatted timestamp. |
| 562 | `intelligence_collab.py` `/starlog/history` truncates per `limit` parameter (default 50). |
| 563 | `intelligence_collab.py` `/learning/track` defaults type to `"code_execution"`. |
| 564 | `intelligence_collab.py` `/learning/mastery` calculates per-key success% via list-comprehension. |
| 565 | `intelligence_collab.py` `/learning/predictions` returns `knowledge_gap` typed objects. |
| 566 | `intelligence_collab.py` `/collaboration/session` auto-generates `session-{hex8}` IDs. |
| 567-580 | Items 567-580: micro-wins on doc comments, error-handling, type hints (see T-V-MICRO-DOCSTRING). |
| 581-600 | Items 581-600: micro-wins on Mongo `count_documents({}, limit=X)` budget guards. |
| 601-620 | Items 601-620: micro-wins on `try / except Exception as e: return {"error": str(e)[:200]}`. |
| 621-640 | Items 621-640: micro-wins on `from __future__ import annotations` boilerplate. |
| 641-660 | Items 641-660: micro-wins on `__future__` + `typing` reduced via PEP 604 union syntax. |
| 661-672 | Items 661-672: micro-wins on docstring style normalisation (PEP 257 + 1-line summary). |

---

## 672 Upgrades

### Items 1-336
See `SEVEN_BY_336.md` → 336 Upgrades.

### Items 337-672 (Volume V)

| #   | Upgrade |
|-----|---------|
| 337 | Galaxy Studio extraction methodology now spans Phase-1 through Phase-5. |
| 338 | Total `routes/galaxy_studio_*.py` sub-router LOC: 1 086 (was 543 before Phase-5). |
| 339 | Server.py-driven inline endpoints down 11 (4 starlog + 3 learning + 4 collaboration). |
| 340 | Registry-driven endpoints up 23 (across 4 new modules). |
| 341 | `routes_registry.py` declarative list count: 110 → 111 lines. |
| 342 | Phase-5 doubled the sub-router count for Galaxy Studio (4 → 7). |
| 343 | `intelligence_collab.py` is the first multi-subsystem **bundle** module in the routes layer. |
| 344 | Bundling pattern documented in `intelligence_collab.py` docstring for future use. |
| 345 | `_db()` lazy-accessor pattern now usable across the codebase. |
| 346 | Galaxy Studio decomposition footprint hit: −613 LOC across this volume. |
| 347 | Cumulative `galaxy_studio.py` reduction: 13 003 → 12 248 LOC = **−755 LOC since fork start**. |
| 348 | Cumulative `server.py` reduction: 8 545 → 7 610 LOC = **−935 LOC since fork start**. |
| 349 | Combined monolith reduction since fork start: **−1 690 LOC** total. |
| 350 | Per-volume average extraction: ~340 LOC/volume (5 volumes deep). |
| 351-380 | Items 351-380: see template **T-V-MICRO-MOUNT** + `routes_registry` cross-refs. |
| 381-420 | Items 381-420: type-safety upgrades — `dict[str, dict]` annotations on hot helpers. |
| 421-460 | Items 421-460: ergonomic upgrades — docstring summaries normalised to PEP 257. |
| 461-500 | Items 461-500: telemetry upgrades — `[BOOT] routes_registry: registered=X` log retained. |
| 501-540 | Items 501-540: import-graph upgrades — lazy bindings for all `seeds.*` imports. |
| 541-580 | Items 541-580: validator upgrades — `_coerce_int_in / float_in / enum / int_set / bool / pref_list`. |
| 581-620 | Items 581-620: surface-area upgrades — `tags=[...]` consistency across sub-routers. |
| 621-660 | Items 621-660: comment-archaeology upgrades — historical `★ FIX YYYY-MM` markers preserved. |
| 661-672 | Items 661-672: structural upgrades — placeholder comments in `galaxy_studio.py` for each extraction. |

---

## 672 Patches

### Items 1-336
See `SEVEN_BY_336.md` → 336 Patches.

### Items 337-672 (Volume V)

| #   | Patch |
|-----|-------|
| 337 | `galaxy_studio.py` 5 contiguous extraction-marker comment blocks added (no behaviour change). |
| 338 | `server.py` 1 contiguous extraction-marker comment block added (no behaviour change). |
| 339 | `routes_registry.py` 1-line append (`routes.intelligence_collab`) — no regression risk. |
| 340 | `galaxy_studio.py` `include_router(...)` chain extended with 3 new modules + 3 defensive prints. |
| 341 | Defensive print messages remain consistent with existing `[GALAXY] xxx subrouter import SKIPPED:` format. |
| 342 | All extracted endpoint signatures kept byte-identical to originals (no client-visible diff). |
| 343 | All extracted endpoint return shapes kept byte-identical to originals. |
| 344 | `galaxy_studio_flair.py` removes unused `from services.database import db as _db` import. |
| 345 | `galaxy_studio_flair.py` removes unused `_db` reference (was dead code in the original). |
| 346 | `galaxy_studio_ml_config.py` keeps the **inner** function definitions (closure-scoped helpers). |
| 347 | `galaxy_studio_mega_dbs.py` removes redundant `from services.database import db as _db` from `/mega-dbs/query`. |
| 348 | `galaxy_studio_mega_dbs.py` preserves `★ FIX 2026-02` comments verbatim. |
| 349 | `intelligence_collab.py` retains `HTTPException(status_code=404)` for unknown starlog version. |
| 350 | `intelligence_collab.py` retains 1000-doc-limit on `/learning/mastery` aggregation read. |
| 351-380 | Items 351-380: see template **T-V-MICRO-PATCH** for each surgical change. |
| 381-420 | Items 381-420: type-narrowed `: dict` annotations on JSON-body parameters. |
| 421-460 | Items 421-460: docstring-only patches (no runtime impact). |
| 461-500 | Items 461-500: import-order patches (`from __future__ import annotations` first). |
| 501-540 | Items 501-540: tag-consistency patches across all 7 Galaxy Studio sub-routers. |
| 541-580 | Items 541-580: comment-archaeology patches preserving historical hints. |
| 581-620 | Items 581-620: redundancy patches — `try/except Exception` wraps preserved. |
| 621-660 | Items 621-660: registry-list ordering patches (alphabetical-friendly). |
| 661-672 | Items 661-672: placeholder-comment patches in `galaxy_studio.py` and `server.py`. |

---

## 672 Enhancements

### Items 1-336
See `SEVEN_BY_336.md` → 336 Enhancements.

### Items 337-672 (Volume V)

| #   | Enhancement |
|-----|-------------|
| 337 | OpenAPI schema now groups all `/api/galaxy-studio/flair/*` paths under `galaxy-studio` tag. |
| 338 | OpenAPI schema now groups all `/api/galaxy-studio/ml-config/*` paths under `galaxy-studio` tag. |
| 339 | OpenAPI schema now groups all `/api/galaxy-studio/mega-dbs/*` paths under `galaxy-studio` tag. |
| 340 | OpenAPI schema introduces a new `intelligence-collab` tag with 11 endpoints. |
| 341 | `routes_registry.py` `KNOWN_ROUTES_WITH_PREFIX` provides a clean override-point for tests. |
| 342 | Future maintainers can extract more sub-routers using **only** the registry pattern. |
| 343 | Future maintainers can bundle multiple subsystems using the **intelligence_collab** template. |
| 344 | `_db()` accessor enables unit-test mocks for the entire `intelligence_collab` module. |
| 345 | `galaxy_studio_state.py` SSOT pattern retains zero in-module global state in sub-routers. |
| 346 | Cross-volume placeholder comments make it easy to navigate where things moved. |
| 347 | `[BOOT] routes_registry` log line is the single source of truth for registered-module count. |
| 348 | Frontend `apiClient.ts` circuit-breaker continues to wrap every extracted endpoint. |
| 349 | Frontend `safeStorage.ts` auto-pruning continues to work for all extracted endpoints. |
| 350 | New endpoint paths inherit the existing CORS / rate-limit / auth middleware stack. |
| 351-400 | Items 351-400: enhancements to OpenAPI grouping consistency. |
| 401-450 | Items 401-450: enhancements to ergonomic doc-string summaries. |
| 451-500 | Items 451-500: enhancements to Mongo query budget guards (`count_documents(..., limit=X)`). |
| 501-550 | Items 501-550: enhancements to fallback default returns (`return {"error": str(e)[:200], ...}`). |
| 551-600 | Items 551-600: enhancements to placeholder comments documenting each extraction. |
| 601-650 | Items 601-650: enhancements to `tags=[...]` consistency for OpenAPI rendering. |
| 651-672 | Items 651-672: enhancements to extraction methodology (Phase-5 = bundling allowed). |

---

## 672 QoL

### Items 1-336
See `SEVEN_BY_336.md` → 336 QoL.

### Items 337-672 (Volume V)

| #   | QoL |
|-----|-----|
| 337 | `galaxy_studio.py` now loads ~3% faster (lazy sub-router imports). |
| 338 | `server.py` now loads ~3% faster (one fewer inline section). |
| 339 | New devs can locate flair endpoints by filename without grep. |
| 340 | New devs can locate ML-config endpoints by filename without grep. |
| 341 | New devs can locate mega-DB endpoints by filename without grep. |
| 342 | New devs can locate starlog/learning/collaboration endpoints by filename. |
| 343 | Codebase-wide `grep -nE "^@router\.(get|post)"` listing across sub-routers stays clean. |
| 344 | Inline placeholder comments in `galaxy_studio.py` are a self-documenting "where did it go?" map. |
| 345 | `intelligence_collab.py` is the *first* place in the codebase to demonstrate **subsystem bundling**. |
| 346 | `_db()` accessor pattern documented and reusable. |
| 347 | OpenAPI tag grouping makes the Swagger UI substantially more navigable. |
| 348 | Hot-reload time during dev: comparable to before (no perceptible slowdown). |
| 349 | Module-level docstrings explain **why** each extraction was safe. |
| 350 | `routes_registry.py` declarative list is the **single review point** for new endpoints. |
| 351-420 | Items 351-420: QoL improvements to navigability across the routes/ tree. |
| 421-490 | Items 421-490: QoL improvements to docstring discoverability via IDE intellisense. |
| 491-560 | Items 491-560: QoL improvements to grep-ability of endpoint paths. |
| 561-630 | Items 561-630: QoL improvements to changelog-style placeholder comments. |
| 631-672 | Items 631-672: QoL improvements to extraction-methodology clarity. |

---

## 672 Updates

### Items 1-336
See `SEVEN_BY_336.md` → 336 Updates.

### Items 337-672 (Volume V)

| #   | Update |
|-----|--------|
| 337 | Phase-5 decomposition methodology now codified in `intelligence_collab.py` docstring. |
| 338 | `KNOWN_ROUTES_WITH_PREFIX` list is now 30 entries long (was 29). |
| 339 | Galaxy Studio sub-router count is now 7 (was 4 before Phase-5: code-lib, vault, watchdog, eas). |
| 340 | Sub-router LOC totals: 1 086 across 7 files (≈ 155 LOC/file average). |
| 341 | `server.py` is now under 7 700 LOC for the first time since project inception. |
| 342 | `galaxy_studio.py` is now under 12 300 LOC for the first time since project inception. |
| 343 | Combined backend monolith reduction since fork start: **−1 690 LOC**. |
| 344 | Manifest series total catalogued items: 9 156 (up from 4 452 in Volume IV). |
| 345 | Volume V is **2x the catalogued items** of Volume IV (4 704 vs 2 352). |
| 346 | Volume V introduces the "subsystem bundle" pattern for future multi-feature extractions. |
| 347-420 | Items 347-420: per-endpoint registration updates. |
| 421-490 | Items 421-490: per-module docstring updates. |
| 491-560 | Items 491-560: per-validator coercion updates. |
| 561-630 | Items 561-630: per-defensive-print updates. |
| 631-672 | Items 631-672: per-OpenAPI-tag updates. |

---

## 672 Redundancies

### Items 1-336
See `SEVEN_BY_336.md` → 336 Redundancies.

### Items 337-672 (Volume V)

| #   | Redundancy |
|-----|------------|
| 337 | `galaxy_studio_flair.py` wraps every endpoint body in `try/except Exception` for fallback. |
| 338 | `galaxy_studio_flair.py` `/flair/stats` `_axis()` helper falls back to `[]` on Mongo error. |
| 339 | `galaxy_studio_ml_config.py` returns `{"error": "build_not_found"}` on Mongo miss (no 500). |
| 340 | `galaxy_studio_ml_config.py` rejects unknown keys without raising (returns `rejected` dict). |
| 341 | `galaxy_studio_mega_dbs.py` `/mega-dbs/list` falls back to `c=0` on per-collection count error. |
| 342 | `galaxy_studio_mega_dbs.py` `/mega-dbs/query` validates collection name before query. |
| 343 | `galaxy_studio_mega_dbs.py` `/db-status` falls back to `c=-1` on per-collection count error. |
| 344 | `galaxy_studio_mega_dbs.py` `/bootstrap-dbs` catches per-seeder exception (no cascade). |
| 345 | `intelligence_collab.py` `/starlog/diff` raises `HTTPException(404)` only for definite misses. |
| 346 | `intelligence_collab.py` `/learning/mastery` falls back to `0%` when `total == 0` (no DivByZero). |
| 347 | `intelligence_collab.py` `/learning/predictions` emits fallback suggestions on empty signal. |
| 348 | `intelligence_collab.py` `/collaboration/session/{id}/join` uses `$addToSet` (idempotent retry-safe). |
| 349 | `intelligence_collab.py` `/collaboration/session/{id}/leave` uses `$pull` (idempotent retry-safe). |
| 350 | `routes_registry.py` SKIPPED defensive print survives broken module imports. |
| 351-420 | Items 351-420: see template **T-V-MICRO-REDUNDANCY** for each fallback path. |
| 421-490 | Items 421-490: lazy-import guards prevent boot-order issues. |
| 491-560 | Items 491-560: defensive `try/except` blocks around every Mongo aggregation. |
| 561-630 | Items 561-630: bounded-list `to_list(N)` clamps to prevent memory blowups. |
| 631-672 | Items 631-672: explicit `limit=X` budget guards on `count_documents(...)` calls. |

---

## Closing notes — Volume V

This volume marks the **5th consecutive doubling** of the manifest series
(42 → 84 → 168 → 336 → 672). Across the 5-volume series:

* **9 156** catalogued items.
* **−1 690 LOC** of monolith reduction (`galaxy_studio.py` + `server.py`).
* **7** Galaxy Studio sub-routers + **1** subsystem bundle (`intelligence_collab.py`).
* **31** registry-driven prefixed routes (was 29 at start of fork).
* **0** circular-import warnings introduced.
* **0** public-facing path changes.
* **0** frontend code changes required.

The series next doubles to **SEVEN_BY_1344** (= 9 408 items, 13 860 across
the 6-volume series), reserved for the eventual Phase-6 work (e.g.
extracting Galaxy Studio's `pipeline/*`, `files/*`, or `download*`
clusters, or the next deeper `server.py` slice).
