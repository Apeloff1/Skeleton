# Milestone: bounded multi-game boomerang experimental curricula — 2026-10-15

The comparative studio can now plan a **finite, reproducible experimental curriculum** for 2–10 user-supplied games in the same study. It selects up to eight eligible single-action interventions distributed across earlier, middle and after checkpoints. A deterministic source-pinned revisit queue brings previous interventions back for one or two later scrutiny passes.

This is not the same as rerunning an opaque model: every treatment uses the already implemented *real native, rights-acknowledged A/B worker runner*, which executes 2–3 fresh emulator workers per baseline and modified controller tape for each selected game. An initial pass and two boomerang revisits are at most 3×8×10×2×3 = **1,440** workers in theory; therefore the **actual enforced launch budget is 480 native executions maximum**, and combinations exceeding it are rejected before any ROM is launched.

The planner is the safe default and requires no emulator or ROM access:

```bash
python3 scripts/run_game_comparison_boomerang.py \
  --manifest /srv/studies/study.json \
  --game title_a --game title_b \
  --treatments 3 --revisit-rounds 2 --repeats 2 \
  --output-dir /srv/studies/boomerang
```

To explicitly execute that 2-game × 3-treatment × 3-round × 2-arm × 2-repeat = **72 fresh native runs** plan:

```bash
python3 scripts/run_game_comparison_boomerang.py \
  --manifest /srv/studies/study.json \
  --registry /srv/approved/cores.json \
  --game title_a --game title_b \
  --treatments 3 --revisit-rounds 2 --repeats 2 \
  --execute --rights-acknowledged --approve-native-runs 72 \
  --output-dir /srv/studies/boomerang
```

The CLI validates the source study, local rights metadata, exact approved core registry and Linux worker sandbox. It saves `boomerang_plan.json`, a resumable `boomerang_progress.json`, and individual `native_trial_XXX.json` receipts plus per-trial hash-verified offline graph dashboards. Each previously completed trial is fully reverified before use or continuation. A mismatched/foreign output directory, tampered input/action/PCM SHA chain or modified schedule fails closed rather than being counted as work.

Per-treatment hashes and the observed repeatable audio/video pattern are aggregated into an evidence-only novelty scoreboard; novelty is **not** intelligent game mastery, generalization, rights clearance, gain of actual neural parameters, or permission to promote Dragon memory. The system does not fabricate results if no native workers can start.

The default three-treatment curriculum works with the current three-action synthetic fixture. `tests/test_game_comparison_boomerang.py` exercises deterministic stages, budget checks, tamper rejection, pending-progress semantics, source rights gating and plan-only execution without real ROMs. The tests are included in the manual-only focused qualification suite, without a new push trigger.

**Important limitations:** This execution is serial over games and treatments, not ten independent simultaneous real-time cores; the pre-existing live two-screen desk supports simultaneous lanes separately. The finite curriculum is a controlled experiment runner, not an unbounded self-training agent. All implementation here is committed source, pending actual native installed-game qualification.

## Resume authority, bounded work per invocation, and honest novelty (second milestone)

`--max-new-treatments N` optionally caps the number of **new** treatments run in one invocation; `0` means all remaining. The explicit `--approve-native-runs` authorization now covers only these fresh executions, never already verified checkpoints. The CLI scans every saved native-trial slot first, rejects any missing interior checkpoint, independently revalidates the recorded SHA-linked controller/frame/audio receipts, and rejects a different installed/approved core registry on resume. Native trials continue only after the full existing prefix has been accepted. Partial execution reports `bounded_native_boomerang_partial_with_verified_resume`, not completed.

The scientific novelty counter now counts only **repeatable post-intervention audiovisual responses with identical pre-intervention observations**. Confounded, unchanged or unstable experiments do not yield a knowledge signal. Fresh run identities, altered input steps and source frame/PCM hashes are excluded from the response fingerprint; thus re-running the same measured response with a different treatment does not automatically produce another novelty credit. Descriptive pattern discovery still does not establish causal mechanics, model parameter gain or promotion authority.

New source-only regression cases cover equivalent measured responses at distinct input checkpoints, no-response exclusion, a changed core-registry authority, and gapped-checkpoint fail-closed resumption. No native game execution is implied by these tests.
