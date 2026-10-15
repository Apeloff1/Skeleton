# Scientific integrity milestone: pre-intervention and repeated A/B gameplay gates — 2026-10-15

A game-frame change after a modified input is only meaningful as controlled *observational evidence* when the two arms were indistinguishable before the perturbation and repeated results are stable. The earlier counterfactual analyzer compared only the first run and could elevate a visual/audio difference that actually started **before** the modified action.

The new analyzer compares **every native fresh-worker A/B repetition**, independently for actual video and native PCM. It requires equal episode tape lengths; exposes per-step counts of different paired repetitions; reports the first fully repeatable difference after the perturbation; and computes per-pair plus mean luminance/audio deltas. It explicitly flags four outcomes:

- `invalid_pre_intervention_divergence`: video or PCM already differed before the selected input; cannot attribute later changes to it.
- `insufficient_native_repeatability`: pre-intervention evidence matched but one of the arms changed across its fresh-worker repetitions.
- `controlled_observable_signal_response_candidate`: input prefix matched, each arm repeated consistently, and a signal differs at or after the perturbation. **Candidate**, not proven game mechanics or intelligent behavior.
- `no_repeatable_audiovisual_difference`: nothing repeatable changed after input; no false learning gain credited.

`verify_counterfactual_input_result` recomputes the measured analysis directly from recorded native frame/audio receipts and **rejects disagreement even if the file-level JSON digest has been recalculated**. The offline dashboard displays the evidence status and an explicit pre-change-divergence warning. The Dragon review intake carries the same conservative grade without promoting it into model weights or authoritative memories.

Added `tests/test_game_comparison_scientific_gates.py` for matched prefix, confounded prefix, nondeterministic arms, unchanged AV signals, and a forged analysis. Wired into the manually triggered focused qualification workflow without adding new push triggers.

This is source-level scientific rigor, not proof that an installed libretro core executed in this chat or that any AI weights improved.
