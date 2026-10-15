# Controlled native input experiments for multi-game learning — October 15, 2026

This is a scientific extension of the 30-game comparative lab, intended to establish **repeatable observations** instead of treating any visual change as learned mechanics.

An operator selects **2–10** games in an existing SHA-pinned comparative study and one meaningful input perturbation at a specified episode step. Each selected game must have a declared and distinct original input action at that step, a source-rights evidence receipt, and an installed/approved compatible libretro core. The tool creates two tapes **identical except for precisely one action**.

It then executes **two or three new isolated native workers per tape**, interleaving the A/B arms to reduce machine-time ordering bias. Across ten games and three repetitions, that is up to sixty actual native worker executions; this is finite, explicit operator work, never a hidden background learning job. Game content is materialized one game at a time, subject to the existing conservative two-copy disk-budget preflight.

Every real episode step records the approved source-media and core SHA-256, input action, native video SHA, native PCM SHA, transition receipt and finite numeric luminance/visual-change/audio evidence. Every arm has its own immutable receipt chain. Within-arm repeats are compared for determinism; between-arm audio/video differences are reported as objective observations.

## Operator example

```bash
python3 scripts/run_game_comparison_counterfactual.py \
  --manifest /srv/studies/genre-history.json \
  --registry /srv/approved/cores.json \
  --game first_title --game second_title \
  --step 2 --replacement left \
  --repeats 2 --rights-acknowledged \
  --output-dir /srv/studies/controlled
```

The two game IDs and paths are placeholders, not evidence of actual game media in the repository. A compatible action must be assigned to each game's first native controller device (joypad/analog policy actions or keyboard key actions). For every game, the replacement action must differ from its baseline tape at the selected step. Actual source rights are asserted by the operator; their legal standing is not independently certified.

Outputs:
- `<study>_controlled_input.html`: **interactive offline report** of actual per-game baseline/changed-input traces, video-change and audio-RMS graphs, repeated-run stability and per-step SHA provenance. Includes no protected game images, music, binary content or external network calls.
- `<study>_controlled_input.json`: every baseline/variant run, exact separate input/action SHA-256 chains, video/audio measurements and per-game controlled comparison.
- `<study>_counterfactual_dragon_review.json`: a much smaller evidence-only summary with measured audio/video differences and repeat consistency. It is **pending separate human/Dragon adversarial review** and cannot automatically update long-term memory or model weights.

## Verification and limits

`verify_counterfactual_input_result()` independently recomputes every locally recorded arm chain, controller tape digest, source/core identity, input index, repeated-worker count and the **single-action-only change**. It rejects modified receipts even if someone recomputes the final JSON document hash without recalculating the per-step chain. The Dragon review bridge refuses an unverified experiment.

This is not a cryptographically signed trusted-execution attestation: an untrusted actor who can forge *all* local run records and chains is not excluded. Held-out gameplay gains, mechanics interpretation, player enjoyment, legal rights and hardware accuracy are separate verification tasks. No language model weights are trained or promoted by this workflow.

Source-only contract fixtures are added in `tests/test_game_comparison_counterfactual.py` and `tests/test_game_comparison_counterfactual_integrity.py`, including adversarial frame/input tampering, and integrated into the **manual-only** focused qualification workflow. No real native ROMs/BIOS or production model training were run by this GitHub source-edit pass.

The HTML report is generated only after recomputing all local experiment receipt hashes. It never presents a tampered or half-finished native run as successful gameplay. Every note about possible game mechanics still requires separate controlled follow-ups and independent review.

Source-only graph/export tests: `tests/test_game_comparison_counterfactual_viewer.py` added to the manual focused qualification workflow; real game rendering has not been executed during this commit.
