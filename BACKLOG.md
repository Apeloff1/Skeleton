# Skeleton Backlog — failed-commit register + forward work

Updated 2026-09-01. Two sections: things that failed and were recovered
(so the failure modes stay visible), and the frontier backlog (what to
build next, ordered).

---

## 1. Failed-commit register

Failed or recovered commits/pushes from the deep-cut campaign. Each entry
is a failure mode worth remembering, not just a hash.

| Commit / attempt | What went wrong | Recovery |
|---|---|---|
| `ca9238c` (2026-08-28) | Scaffold rewrote `api/server.py` + `api/errors.py` *without reading them first* — clobbered the full lifespan app (AppState, probes, metrics) with a thin version | Restored verbatim from ref `bdca180b` in `b4790a1`. Rule born: extend-only, read before touching |
| First restore attempt of `b4790a1` | Push result came back as a directory listing (mis-shaped dispatch), restore silently didn't land; main still had the thin scaffold | Caught by re-reading `api/server.py` on main; re-pushed successfully as `b4790a1` |
| CHANGELOG rewrite (docs pass, `bc4fa6b`) | The rewrite dropped the original Feb/Aug 2026 body behind a "(Previous content retained below.)" marker without actually retaining it | Flagged honestly at the time; original content was never re-verified post-push — **re-verify and restore if clipped** (see §3, F-1) |
| Repeated empty/mis-shaped `EXECUTE_TOOL` calls | Several tool dispatches failed with missing-parameter errors mid-pass (docs read, plan pushes) | Retried with correct args; no content lost |

Lesson pattern: every failure was a *write made before a read* or a *push
trusted without re-verification*. Both are now rules.

---

## 2. Frontier backlog — ordered by leverage

### Tier 1 — close the live seams (small, high-value)

1. **F-1. Verify CHANGELOG integrity** — confirm the pre-2026-08 entries
   survived `bc4fa6b`; restore from git history if clipped.
2. **F-2. Feedback endpoint for plane weights** — `POST /retrieval/feedback`
   (used plane list) → `quad` learner `observe()`. The learner is built;
   the loop isn't wired.
3. **F-3. Rot-triggered compaction in the API** — run
   `RotGuardedCompactor.process` inside the memory/query path when turns
   are supplied.
4. **F-4. HandoffRegistry × AgentMesh** — `submit` envelopes where the mesh
   picks the assignee by capability; one adapter class.
5. **F-5. Verifier gate on forge materialise** — `CodeVerifier.verdict`
   into a `VerificationLoop` before materialise returns (revise-until-green).

### Tier 2 — frontier pushes (medium, differentiating)

6. **F-6. Mixture-of-depths for the neo transformer** — dynamic per-token
   compute allocation in `cortex/transformer.py`; the 2026 MoD results
   show real FLOP savings at iso-quality.
7. **F-7. Skills-as-files context architecture** — the RalphLoop/filesystem
   pattern: reload task state from disk each fresh-context iteration
   instead of growing one context forever. Fits the cockpit's existing
   ledger + tensor state.
8. **F-8. Memory-poisoning guards for the blackboard** — shared agent
   stores need provenance + confidence quarantine on writes; the
   blackboard has confidence but no adversarial screening.
9. **F-9. N+1 tool-call storm suppression** — production pattern: batch or
   dedupe identical tool calls within a turn window; `kernel/dedup.py`
   already exists — compose.
10. **F-10. Self-improvement over prompts** — `ImproveLoop` driving
    `services/cag.py` prefix text variants scored by downstream answer
    quality (needs the F-2 feedback loop first).

### Tier 3 — structural (bigger, schedule carefully)

11. **F-11. Track E cleanup** — root sprawl moves, SEVEN_BY physical moves,
    godot binary to LFS, shim deletion. Local git ops.
12. **F-12. H5.4 cortex persistence** — genesis twin vs live singleton once
    `$SKELETON_OWN` exists in the container.
13. **F-13. EconomicOptimiser audit** — `intelligence/economic.py` predates
    the cascade router; reconcile the two routing contracts.
14. **F-14. Speculative RAG** — pre-fetch likely-needed documents during
    the planning phase of a pipeline run (compose quad + composer).

## Definition of SOTA (working)

Skeleton is at SOTA when: every retrieval/memory/learn path has a live
feedback loop (F-2, F-10), context health is monitored and repaired in the
serving path (F-3), agent coordination is envelope-typed end to end (F-4),
and generated artefacts pass a verifier gate before shipping (F-5). Tier 2
is where the system stops catching up and starts pushing.
