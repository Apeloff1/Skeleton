# Skeleton Backlog — failed-commit register + forward work

Updated 2026-09-16 (F-11 root-sprawl partial cleanup). Original register dated 2026-09-01. Two sections: things that failed and were recovered
(so the failure modes stay visible), and the frontier backlog (what to
build next, ordered).

---

## 1. Failed-commit register

Failed or recovered commits/pushes from the campaign. Each entry is a
failure mode worth remembering, not just a hash.

| Commit / attempt | What went wrong | Recovery |
|---|---|---|
| `ca9238c` (2026-08-28) | Scaffold rewrote `api/server.py` + `api/errors.py` *without reading them first* — clobbered the full lifespan app (AppState, probes, metrics) with a thin version | Restored verbatim from ref `bdca180b` in `b4790a1`. Rule born: extend-only, read before touching |
| First restore attempt of `b4790a1` | Push result came back as a directory listing (mis-shaped dispatch), restore silently didn't land; main still had the thin scaffold | Caught by re-reading `api/server.py` on main; re-pushed successfully as `b4790a1` |
| CHANGELOG rewrite (docs pass, `bc4fa6b`) | The rewrite dropped the original Feb/Aug 2026 body behind a "(Previous content retained below.)" marker without actually retaining it | **Confirmed 2026-09-01**: read of current CHANGELOG.md shows the marker with nothing below it — the Phase-1→9 and Godot-crate entries are gone from the file. They survive in git history (ref 4c96683 / any commit before bc4fa6b) and can be restored from there when convenient — tracked as F-1 |
| `a5ff0a0` (2026-09-01) | A mis-shaped dispatch pushed a junk `scratch_marker.txt` placeholder to the repo root | Deleted immediately via `GITHUB_DELETE_FILE` (`9c0fe0a`). Rule reinforced: never push a placeholder to "test" a shape |
| Repeated empty/mis-shaped `EXECUTE_TOOL` calls | Several tool dispatches failed with missing-parameter errors mid-pass (docs read, plan pushes) | Retried with correct args; no content lost |

Lesson pattern: every failure was a *write made before a read* or a *push
trusted without re-verification*. Both are now rules.

**Repo drift note (2026-09-01):** the repo gained `skeleton/organism/`,
`skeleton/social/`, `skeleton/galaxy/` planes and a CommandDeck while this
session's waves were landing (CHANGELOG entries 2026-08-31 → 2026-09-01).
Those planes are out-of-scope for this register — audit separately.

---

## 2. Frontier backlog — ordered by leverage

Updated 2026-09-16. Tier-1 seams F-1..F-10, the Tier-2 F-6 frontier push,
and F-13 economic/cascade reconciliation are **landed**; do not re-open them
without a regression.

### Landed (keep visible — failure modes + PR anchors)

| Item | PR | Notes |
|---|---|---|
| F-1 CHANGELOG restore | #23 | pre-Aug-2026 body restored |
| F-2 `/retrieval/feedback` | #10 | plane-weight `observe()` wired |
| F-3 Rot-triggered compaction | #4 | `/memory/query` + `RotGuardedCompactor` |
| F-4 HandoffRegistry × AgentMesh | #6 | `skeleton/swarm/mesh_handoff.py` |
| F-5 forge VerificationLoop | #7 / #28 | materialise revise-until-green + E2E deepen |
| F-6 Mixture-of-Depths | #290 | opt-in residual-RMS per-token depth routing + depth telemetry/profiler |
| F-7 skills-as-files context | #224 | fresh disk reload loop + bounded context cards + GameForge bank bridge |
| F-8 blackboard poison guards | #18 | provenance + quarantine |
| F-9 N+1 tool-call suppression | #20 | compose `kernel/dedup.py` |
| F-10 PromptImproveDriver | #31 | ImproveLoop over prefix variants |
| F-13 EconomicOptimiser × CascadeRouter | #277 | shared economic model registry, cascade planning, real model IDs, budget/cost accounting |
| P6 policy enforcement | #13 | CodeVerifier + repair/verify gates |

### Live ops state — resolved blockers, keep green

The previous CI-1..CI-3 blockers are no longer active backlog items. Keep
them as regression contracts rather than re-opening stale branches.

1. **CI-1. Jeeves import + CLI shims — RESOLVED.** Current main exports
   `Jeeves` from `skeleton/jeeves/core.py`, and the canonical CI job executes
   `python -m skeleton eras`, `plan`, `cockpit`, and `walk` as smoke gates.
2. **CI-2. Cortex restore — RESOLVED.** PR #25 merged on 2026-09-12,
   restoring the full cortex API and the GameForge-facing compatibility path.
3. **CI-3. Cockpit smoke CI wire — RESOLVED ON MAIN.** PR #29 itself was
   closed without merge, but current `.github/workflows/ci.yml` contains the
   dedicated `cockpit-smoke` job and runs `scripts/cockpit-smoke.sh`.

Recent backlog hygiene on 2026-09-15 also retired stale overlapping work:
issue #255 was completed by merged PR #257, PR #237 was superseded by merged
#247, and the competing F-6 branches #133/#260 were retired in favor of merged
#290.

### Tier 2 — frontier push — LANDED

**F-6. Mixture-of-Depths for the neo transformer — LANDED via #290.** The
current implementation adds dynamic per-token inference depth while preserving
the full-depth path, training/backprop, and snapshot interchange. `cortex/moe.py`
remains Mixture-of-*Experts* and is a separate mechanism.

### Tier 3 — structural (next work, schedule carefully)

1. **F-11. Track E cleanup — IN PROGRESS.**
   - [x] Relocate standalone root planning/delivery records into `docs/`:
     `BUILD_PLAN.md`, `CONSOLIDATION.md`, and `DELIVERY.md`.
   - [ ] Complete remaining root-sprawl cleanup after reference audit.
   - [ ] Complete `SEVEN_BY_*` physical moves/archival.
   - [ ] Move the Godot binary to LFS without losing the tracked engine artifact.
   - [ ] Delete compatibility shims only after import/caller verification.
2. **F-12. H5.4 cortex persistence** — genesis twin vs live singleton once
   `$SKELETON_OWN` exists in the container.
3. **F-14. Speculative RAG** — pre-fetch likely-needed documents during
   the planning phase of a pipeline run (compose quad + composer).
   Adjacent: `cortex/speculate.py` is token continuation, not RAG prefetch.
4. **F-15. Organism/social/galaxy plane audit** — the repo grew three
   planes while the waves landed (see §1 drift note). Same size-filtered
   read methodology as the deep-cut campaign, when their churn settles.

## Definition of SOTA (working)

Tier-1 SOTA seams, F-6 Mixture-of-Depths, and F-13 economic/cascade
reconciliation are landed in code. The former CI-1..CI-3 blockers are resolved
on main; the remaining structural queue is F-11, F-12, F-14, then F-15.
