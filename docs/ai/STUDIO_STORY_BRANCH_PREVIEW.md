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
