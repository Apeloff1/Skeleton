# Explicit ten-game study-local Q-learning — 2026-10-15

The comparative studio now has a real, optional learning implementation using the **existing Jeeves `GamePolicyLearner.train_offline`**, not invented neural-network weights. After executing real approved libretro game frames and generating a canonical bounded offline trace for each game, the operator may choose to update **one independent tabular Q policy for that exact game/environment**. The trained snapshot, policy SHA-256, pretraining SHA-256 and number of actual Q updates are returned in the study JSON and summarized in the offline viewer. The game/study may use up to ten native sessions concurrently, with separate per-game policies.

This explicitly does **not** combine Q tables across distinct console state spaces, train the main LLM transformer, prove improvements on held-out gameplay, validate ROM licensing, or promote production weights.

The run is guarded by every one of these conditions: `--run` using an operator-approved current libretro registry, a chosen `--batch N` limited to <=10 games, `--without-previews` to retain memory capacity, `--train-shadow-policy`, and `--rights-acknowledged`. Each selected game must also have a non-null SHA-256 `rights_evidence_digest` in its manifest. The latter is an explicit operator assertion and **not** independent legal verification; only an authorized operator with rights-cleared homebrew sources should opt in. The preexisting real training algorithm receives per-update host authorization and is episode-atomic; on failure it reverts the incomplete learner episode.

```bash
python3 scripts/compare_game_study.py \
  --manifest /srv/studies/genre_evolution_one.json \
  --registry /srv/skeleton-emulators/cores.json \
  --output-dir /srv/study-reports --run --batch 0 \
  --without-previews --train-shadow-policy --rights-acknowledged
```

`<study_id>.result.json` contains full bounded local Q snapshots and canonical native-trace receipts; the viewer shows per-game updates and policy identities but does not expose game ROMs. No training was executed in the source-implementation chat. This is an explicit on-machine operator command for eligible rights-cleared materials only.

The 30-game study remains partitioned into cohorts of up to ten; to train another cohort, repeat with `--batch 1` or `--batch 2` after independent review. These local learning snapshots are not canonical production shadow weights. Further promotion requires independent safety, rights, accuracy, held-out evaluation and the existing high-impact shadow-weight permission gate.
