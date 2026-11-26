# Original quest runtime: offline application entrypoint

The recovered B028 objective state machine, B030 mechanic-pack composition,
and B037 constraint-guided synthesis already exist on the current main
snapshot (08158da161c96e52348805894f7c39817c93b9b9). Their existing
`original_quest_slice` composition is reused rather than forked.

This application boundary provides an installed console command
`skeleton-original-quest` and the equivalent source command
`python -m skeleton.app.original_quest_cli`. Input and output are JSON via
standard streams. No file is opened by the command, no existing game is
modified, and no model or external engine is invoked.

## Build

Example request JSON (save as request.json using an editor):

```json
{
  "schema": "skeleton.original_quest.request.v1",
  "slice_id": "lantern-harbor",
  "packs": [
    {"id": "movement", "provides": ["movement"]},
    {"id": "quest", "provides": ["quests"], "requires": ["movement"]}
  ],
  "pack_ids": ["movement", "quest"],
  "world": {
    "start": "village",
    "edges": {"village": ["forest"], "forest": ["cave"], "cave": []},
    "npcs": {"ranger": "forest"}
  },
  "policy": {
    "allowed_reward_kinds": ["xp"],
    "max_reward_per_step": 4,
    "max_total_reward": 20,
    "banned_terms": ["forbidden"]
  },
  "seed": 7,
  "quest_length": 3
}
```

```sh
python -m skeleton.app.original_quest_cli build < request.json > receipt.json
```

## Verify with independent input

An independent caller must supply the original authorized request and the
receipt under the exact keys `request` and `receipt`. Do not take the
request's authority from the receipt. Verification regenerates the actual
mechanics, quest and objective-event replay and compares the complete canonical
JSON bytes. The receipt identifies the request by SHA-256 but is not a signature,
proof of authorship, package attestation, or authorization for publication.

For example, using a trusted local Python installation:

```sh
python -c "import json; print(json.dumps({'request':json.load(open('request.json')), 'receipt':json.load(open('receipt.json'))}))" | python -m skeleton.app.original_quest_cli verify
```

Exit status 0 indicates an abstract replay match; 1 indicates rejected input,
and argparse uses 2 for malformed command invocation. Requests, receipts and
the complete verification envelope are bounded to 2 MiB of canonical JSON.
Duplicate JSON keys, dangling locations, malformed capabilities, unknown
fields, unbounded collections, nonfinite numbers and changed proof bytes
are rejected. This command never accepts caller-supplied native or release
qualification.

## Source and installed qualification

```sh
python -m pytest -q skeleton/testing/test_original_quest_cli.py skeleton/testing/test_original_quest_slice.py skeleton/testing/test_constraint_quest_synthesis.py skeleton/testing/test_genre_template_composition.py skeleton/testing/test_quest_objective_runtime.py
python -m compileall -q skeleton/app/original_quest_cli.py
```

After a wheel is built and installed in a clean environment, exercise the
installed command's build and verify paths using the same independent input.
That installation check is distinct from module-level acceptance. Backend
authorization, UI/project cockpit integration, native Godot execution, device
tests, release provenance, security and required exact-head checks remain
independent. No merge or release authorization.
