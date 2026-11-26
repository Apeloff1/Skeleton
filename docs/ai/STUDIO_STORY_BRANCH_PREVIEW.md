# Source-bound offline story branch preview

The existing interactive HTML5 authored quest director now offers a **Preview**
button next to each currently available source-authored action. Preview
calculates the hypothetical reward/choice-effect facts and newly eligible
sandbox endings without modifying the browser checkpoint. Choosing an action
still changes the checkpoint, and restarting or restoring clears stale preview
text. All preview output is inserted through textContent, never HTML.

The Python `preview_browser_story_choice` API independently parses the
untrusted browser transcript with duplicate-key and nonfinite rejection,
verifies its exact quest-source digest, replays every choice through the
canonical quest state machine, and simulates one new authorized action. The
response includes base/candidate session digests and unmet predicates, with
explicit false external-evidence, native-runtime, and release claims.

The browser's choice-effect lookup now requires an **own** JSON property.
Valid authored choices such as `toString` cannot accidentally traverse
JavaScript Object.prototype and crash the sandbox simulation. A Node VM
regression exercises real browser JavaScript for preview, restore, and this
prototype-key edge case. Python regressions exercise source binding, action
validation, authorization, replay parity, and nonmutation.

This feature does not prove actual NPC behavior, external consequences,
rights, native engine parity, device qualification, or consumer release.

Focused validation once an exact-head runner is available:

```sh
python -m pytest -q tests/test_studio_ecosystem_story_review.py \\
  tests/test_studio_ecosystem_story_html.py \\
  tests/test_studio_story_browser_js_runtime.py
```

## Nonmutating checkpoint comparison and undo

The offline story director can now undo its last source-authored action, or
compare a pasted checkpoint with the current state. Comparison requires the
same canonical JSON, source lease, and legal action order as restore, and
reports the common action prefix plus newly gained/lost authored sandbox
endings. It never overwrites the current session. The Python
`compare_browser_story_receipts` independently replays **both** untrusted
histories through the authoritative quest state machine, refusing duplicate
keys, forged release claims, stale sources, or illegal actions.

The Node runtime harness covers undo and comparison without mutation. The
Python suite covers independent replay, session digests, and hostile input.

## Typed Jeeves read-only tool

`studio_original_story_checkpoint` exposes the same canonical preview and
checkpoint comparison through a closed request schema, exact quest-source
lease, bounded UTF-8 checkpoint strings, and explicit operator authorization.
The Jeeves game orchestrator delegates to the canonical Python replay. Both
canonical and mirror Jeeves module paths carry byte-identical tool and
orchestrator implementations. The tool returns request/result digests and
explicitly denies file-write, browser-trust, native, external-evidence, and
release claims. It never uses model-provided authorization fields.

## Source-leased operator CLI

The read-only `studio_story_checkpoint_cli` invokes the exact Jeeves typed
replay contract. Its POSIX input loader accepts only owner-private regular
JSON files by basename from a pinned current-directory descriptor; no symlink,
FIFO, hardlink, traversal, oversized file, or changing file is accepted. It
never writes an output file or alters a checkpoint. Platforms lacking secure
POSIX descriptor flags fail closed; Windows is not qualified by this CLI.

Example after exporting a browser checkpoint to an owner-private file:

```sh
chmod 600 current.json candidate.json
python -m skeleton.ai.game_builder.studio_story_checkpoint_cli \\
  --project-id studio_arena_fighting_glacial_fjord \\
  --quest-source-digest <64-hex-canonical-quest-digest> \\
  --checkpoint-file current.json --compare-file candidate.json \\
  --trusted-local-operator
```

For preview, replace `--compare-file` with `--preview-stage STAGE`
and `--alternative CHOICE`. The tool emits JSON to stdout with replay
digests and explicit false release/native/evidence flags.
