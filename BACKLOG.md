# Skeleton Backlog — failed-commit register + forward work

Updated 2026-09-15 (F-6 implementation + CI register reconciliation). Original register dated 2026-09-01. Two sections: things that failed and were recovered
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

Updated 2026-09-15. Tier-1 seams F-1..F-5, F-7 and F-8..F-10 are
**landed**; do not re-open them without a regression.

### Landed (keep visible — failure modes + PR anchors)

| Item | PR | Notes |
|---|---|---|
| F-1 CHANGELOG restore | #23 | pre-Aug-2026 body restored |
| F-2 `/retrieval/feedback` | #10 | plane-weight `observe()` wired |
| F-3 Rot-triggered compaction | #4 | `/memory/query` + `RotGuardedCompactor` |
| F-4 HandoffRegistry × AgentMesh | #6 | `skeleton/swarm/mesh_handoff.py` |
| F-5 forge VerificationLoop | #7 / #28 | materialise revise-until-green + E2E deepen |
| F-7 skills-as-files context | #224 | fresh disk reload loop + bounded context cards + GameForge bank bridge |
| F-8 blackboard poison guards | #18 | provenance + quarantine |
| F-9 N+1 tool-call suppression | #20 | compose `kernel/dedup.py` |
| F-10 PromptImproveDriver | #31 | ImproveLoop over prefix variants |
| P6 policy enforcement | #13 | CodeVerifier + repair/verify gates |
| CI-1 Jeeves import/API compatibility | main | `skeleton.jeeves.core.Jeeves` exists and package exports both `Jeeves` and `JeevesCore`; stale blocker removed |
| CI-2 cortex restore | #25 | merged; no longer depends on CI-1 |
| CI-3 cockpit-smoke CI | main | dedicated `cockpit-smoke` job is present in `.github/workflows/ci.yml` |

### Live ops status (reconciled 2026-09-15)

The former CI-1..CI-3 merge blockers are already represented on current
`main`. They stay visible in the landed table above so a stale register does
not send later work back through completed recovery paths. Re-open only on a
new regression with a failing check or reproducer.

### Tier 2 — frontier pushes (next differentiating work)

1. **F-6. Mixture-of-depths for the neo transformer** — dynamic per-token
   compute allocation in `cortex/transformer.py`. Note: `cortex/moe.py` is
   Mixture-of-*Experts* (different). Active implementation: sparse FFN routing
   with dense attention and a 1.0 compatibility default, so existing snapshots
   keep their current behavior.

### Tier 3 — structural (bigger, schedule carefully)

2. **F-11. Track E cleanup** — root sprawl moves, SEVEN_BY physical moves,
   godot binary to LFS, shim deletion. Local git ops.
3. **F-12. H5.4 cortex persistence** — genesis twin vs live singleton once
   `$SKELETON_OWN` exists in the container.
4. **F-13. EconomicOptimiser audit** — `intelligence/economic.py` predates
   the cascade router; reconcile the two routing contracts.
5. **F-14. Speculative RAG** — pre-fetch likely-needed documents during
   the planning phase of a pipeline run (compose quad + composer).
   Adjacent: `cortex/speculate.py` is token continuation, not RAG prefetch.
6. **F-15. Organism/social/galaxy plane audit** — the repo grew three
    planes while the waves landed (see §1 drift note). Same size-filtered
    read methodology as the deep-cut campaign, when their churn settles.

## Definition of SOTA (working)

Tier-1 SOTA seams (F-2..F-5, F-7, F-10) and the former live-ops CI gaps are
landed in code. Remaining bar: keep main CI green, land Tier-2 differentiation
(F-6 MoD), then continue through the structural Tier-3 work without reviving
stale blockers.