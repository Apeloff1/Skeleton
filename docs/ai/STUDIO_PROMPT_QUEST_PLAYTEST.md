# End-to-end original quest playable handoff

The operator first compiles an original typed prompt plan and publishes its
immutable private receipt. The playtest workflow reopens that exact receipt,
checks the caller's receipt digest, runs the canonical authored quest engine,
searches for an ending witness, and replays the final quest session. A found
witness contains only *sandbox quest* evidence; unobserved evidence cannot be
manufactured. A budget-exhausted search is inconclusive.

```bash
python -m scripts.studio_prompt_quest_playtest_cli \
  --plan-directory PRIVATE_PLAN_DIR --expected-compilation RECEIPT_SHA256 \
  --target-ending safe --max-states 512 --max-depth 16
```

Use `--publish-witness PRIVATE_WITNESS_DIR` for a private immutable ending
receipt, or `--html-preview` for a read-only CSP-restricted HTML result.
The static Jeeves tool `studio_original_prompt_quest_playtest` accepts a
source-leased compilation without granting authoring or filesystem access.
No native runtime, device qualification, copyright clearance or release is
asserted.
