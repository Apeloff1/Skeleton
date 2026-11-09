# Comparative Game Study — Jeeves × Dragon (2026-10-15)

## Implemented boundaries

This is a **working integration path** over the existing operator-approved, isolated libretro runtime: the comparative study has 2–30 game/edition rows, 1–10 simultaneously active native game sessions, and is scheduled in batches of at most ten. An omitted pair list expands to the bounded all-pairs comparison matrix (maximum 435 comparisons for 30 games), without loading an additional emulator for every pair. Pairs can use two different cores, two different games, or two core/edition variants of one installment.

It separates **three different chronological concepts**:

- `series_phase` — earlier, middle or after *installments in a declared series*; release order remains stable across multiple separate studies of a large series.
- `phases.earlier/middle/after` — three **real native audiovisual observations** sampled during each game's bounded input tape.
- `build_parameter_candidate` — a proposed numeric design hypothesis attributed to an actual viewer, Dragon or Jeeves note, never a value magically extracted from game ROM bytes.

For every executed game, the existing host captures actual isolated native frames, PCM digest/counters, brightness/audio RMS/visual-change metrics, and canonical offline hash-chained trace evidence. A native failure produces `native_execution_failed` with **no fabricated screenshots**. A second actual reset/trace pass binds each game's observations to existing game learning ingestion rules. Screenshots are optional bounded thumbnail data URIs in user-local evidence only; original game ROMs, BIOS, movie/audio assets, full videos or game executable bytes are **not** copied into the Dragon knowledge record.

The offline HTML viewer shows selected games side by side at each real checkpoint, relative metrics, series/installment ordering, question prompts, reviewer/Dragon notes and manually proposed build parameters. Notes edited in the page remain **local** until the viewer exports a JSON note pack. The CLI can re-import it on the next pass; reviewed cards with exact stage SHA-256 evidence are separately exported for subsequent authenticated Dragon Family review/consent. Neither this bridge nor the report writes directly to Dragon custody, crawls new articles/videos, trains neural weights, copies protected expression into a new game, or claims gameplay success.

## JSON input contract

`schema_version` must be `skeleton.game.comparative_study.v1`. Supply **2–30 games**, 1–10 `max_active`, zero or more pairs, and zero or more notes. A zero-length `pairs` array means the complete all-pairs study matrix. Each game has exact fields (no extra fields):

```json
{
  "schema_version": "skeleton.game.comparative_study.v1",
  "study_id": "genre_evolution_one",
  "title": "Two-original-homebrew evolutionary comparison",
  "max_active": 2,
  "games": [
    {
      "id": "prototype_a", "title": "Original homebrew A",
      "series_id": "original_series", "release_order": 1, "release_year": 2025,
      "series_phase": "earlier", "target_id": "nes", "core_id": "fceumm",
      "source_path": "/srv/lawful-homebrew/prototype-a.nes",
      "source_sha256": "<replace with exact 64-character SHA-256 of lawful ROM>",
      "rights_evidence_digest": null,
      "actions": ["idle", "right", "a", "left", "idle", "a"],
      "seed": 10, "frames_per_step": 2, "controller_devices": ["joypad"]
    },
    {
      "id": "prototype_b", "title": "Original homebrew B",
      "series_id": "original_series", "release_order": 2, "release_year": 2026,
      "series_phase": "middle", "target_id": "snes", "core_id": "snes9x",
      "source_path": "/srv/lawful-homebrew/prototype-b.sfc",
      "source_sha256": "<replace with exact 64-character SHA-256 of lawful ROM>",
      "rights_evidence_digest": null,
      "actions": ["idle", "right", "a", "left", "idle", "a"],
      "seed": 10, "frames_per_step": 2, "controller_devices": ["joypad"]
    }
  ],
  "pairs": [{"left_id": "prototype_a", "right_id": "prototype_b", "questions": [
    "How does measured audiovisual response differ across checkpoints?",
    "What abstract original level-design improvements should be examined by a reviewer?"
  ]}],
  "notes": []
}
```

Source paths and hashes above are **illustrative placeholders** and do not represent installed games. Substitute actual operator-owned lawful game data and a qualified Linux native emulator installation. `series_phase` must be nondecreasing by release order; any of the three series eras may be absent in a small study. For game notes:

```json
{
  "note_id": "viewer_camera_a", "author": "viewer",
  "game_ids": ["prototype_a", "prototype_b"],
  "checkpoint": "middle", "dimension": "camera",
  "claim_type": "hypothesis",
  "text": "Investigate a wider original playfield to reduce off-screen decision pressure.",
  "review_status": "pending",
  "build_parameter": {"name": "camera_lookahead_tiles", "value": 3.0, "units": "tiles"}
}
```

The note is an operator-authored hypothesis, not verified gameplay evidence, an exact source-game parameter, a license grant or a promoted training weight.

## Operator commands

Plan only (no ROM loaded, no gameplay execution or licensed content access):

```bash
python3 scripts/compare_game_study.py \
  --manifest /srv/studies/genre_evolution_one.json \
  --output-dir /srv/study-reports
```

Actual operator-approved native execution, all batches sequentially, at most `max_active` real sessions at a time:

```bash
python3 scripts/compare_game_study.py \
  --manifest /srv/studies/genre_evolution_one.json \
  --registry /srv/skeleton-emulators/cores.json \
  --output-dir /srv/study-reports --run
```

For a 30-game study, choose `--batch 0`, `--batch 1`, or `--batch 2` to execute only one cohort (depending on `max_active`). To reduce report size, add `--without-previews`. After viewing and annotating the HTML, export notes and re-import them with `--notes-json path/to/genre_evolution_one_viewer_notes.json`.

Outputs are atomic, permission-limited files:

- `<study_id>.plan.json` — exact non-executing plan, all series and pair indexing, concurrency limits.
- `<study_id>.result.json` — actual native observations and failures, objective side-by-side comparisons, source-digested user/AI notes, and proposed design parameters.
- `<study_id>.viewer.html` — standalone private side-by-side browser viewer with editing and notes export.
- `<study_id>.dragon-intake.json` — reviewed-source candidates with exact native evidence, **pending** external Dragon consent/verification.

## Current limits and separate training gate

One study is capped at 30 games; major long-running series can be split into many named studies with consistent `series_id` and `release_order`. ROM-style single-file assets are currently capped at 16 MiB by the existing native inline content admission; large disc/multi-file games require a subsequent integration with the existing multi-file `GameContentBundle` pathway. A recognized ROM/core recipe alone is not an approved runnable emulator.

The code implements evidence collection and **reviewable knowledge preparation**, not optimization of production Jeeves/Dragon parameters or confirmed model-weight gain. To promote parameters: independent rights/consent, actual emulator compatibility, annotated observations, adversarial review, held-out outcome tests and the separate existing weight owner must accept the work. No new game mechanics or copyrighted expression are automatically assembled from protected titles.
