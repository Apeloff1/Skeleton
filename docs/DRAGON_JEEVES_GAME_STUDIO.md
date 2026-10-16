# Dragon → Jeeves original-game production bridge

The local game workspace has **four new Dragon commands**, executed through
`python -m skeleton dev game jeeves`. They reuse the canonical Dragon
`review_recording`, `GameMechanicsMemory`, and `DragonGameForge` implementations
rather than inventing game mechanics or pretending that a game was played.

## 1. Prepare a reviewed observation packet

After an authorized capture/review, place this small JSON packet at
`<project>/design/dragon_study.json` (a **direct child** of `design/`):

```json
{
  "schema": "skeleton.dragon.jeeves_study.v1",
  "project": "my-original-game",
  "owner": "local-reviewer",
  "game_label": "Authorized research session",
  "duration_ms": 10000,
  "capture_consent": true,
  "analysis_consent": true,
  "rights_attested": true,
  "observations": [
    {
      "timestamp_ms": 1000,
      "source_frame_ms": 1000,
      "label": "responsive traversal",
      "confidence": 0.9,
      "description": "Character stops in predictable distance",
      "mechanic": "movement",
      "preference": "enjoyed",
      "user_confirmed": true,
      "reviewer_note": "Observer and player confirmed this preference"
    }
  ]
}
```

These assertions come from the operator: **rights, consent, source originality,
quality, and actual recording are not independently verified**. This bridge
does not acquire media, decompile ROMs, copy reference assets, or retain video.

## 2. Review, ingest, create a Dragon prototype, approve a handoff

```bash
python -m skeleton dev game jeeves dragon-review --project ./my-original-game --source design/dragon_study.json
python -m skeleton dev game jeeves dragon-ingest --project ./my-original-game --source design/dragon_study.json --approve <source_sha256>
python -m skeleton dev game jeeves dragon-plan --project ./my-original-game --source design/dragon_study.json --genre platformer --target gameboy
python -m skeleton dev game jeeves dragon-adopt --project ./my-original-game --source design/dragon_study.json --genre platformer --target gameboy --approve <handoff_sha256>
```

Copy the source SHA-256 from `dragon-review` and the complete handoff SHA-256
from `dragon-plan`; placeholders are **not** literal. A mistake in either
digest is rejected. Review and plan are read-only. Ingest idempotently saves
reviewed, non-video observations in the project's local SQLite database.
Adopt writes a **create-only** JSON handoff to
`.jeeves/dragon_handoffs/<handoff_sha256>.json`. It can never overwrite an
approved handoff. Each handoff includes original game mechanic objectives,
actions, responses, feedback, evidence fingerprints, evaluation warnings,
and explicit unverified flags.

## 3. Give approved Dragon design context to Jeeves

```bash
python -m skeleton dev game jeeves propose --project ./my-original-game --kind mechanic --brief "Invent an original traversal system with readable stopping and multiple paths" --dragon-digest <handoff_sha256>
python -m skeleton dev game jeeves review --project ./my-original-game --digest <proposal_sha256>
python -m skeleton dev game jeeves apply --project ./my-original-game --digest <proposal_sha256> --approve <proposal_sha256>
```

The `--dragon-digest` option is **opt-in** for the `propose` action. The
model receives only bounded reviewed *design* context—not stored captures
or arbitrary SQLite rows. Proposals have a v4 identity envelope binding the
Dragon handoff, project configuration, and existing market/direction evidence.
When review or apply detects changed inputs, it **fails closed** instead of
using stale Dragon findings. The existing media benchmark requirements still
apply for asset, animation, cutscene, and music proposals.

The accepted artifact is a **new local design draft**. It is not executable
game content, trained weights, proof of industry-grade quality, or a release.
A separate, real game build, playthrough, and acceptance run is required.
Use `python -m unittest tests.test_jeeves_dragon_game_handoff` for a focused
local regression check; this is not an automatic merge-blocking CI gate.
