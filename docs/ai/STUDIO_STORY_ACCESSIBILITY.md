# Source-bound accessible original story reading editions

Studio A compiles the canonical original narrative, scene goals, authored decisions, alternatives and ending predicates into two **deterministic text formats**: a screen-reader-friendly Markdown reading edition and a WebVTT cue track with conservative synthetic reading timings. It never fabricates dialogue, audio, physical gameplay, rights clearance or release evidence.

After compiling the current canonical source and obtaining its quest source digest, an authorized local operator may run:

```sh
python -m skeleton.ai.game_builder.studio_story_accessibility_cli \
  --project-id studio_arena_fighting_glacial_fjord \
  --quest-source-digest <current-64-hex-quest-digest> \
  --format webvtt --output-file story.vtt --trusted-local-operator
```

For a printable text reading edition use `--format markdown --output-file story.md`. The output directory must be owner-private (0700), output is a new 0600 regular file, and existing files are never overwritten. The same compiler is available as the closed-schema Jeeves tool `studio_original_story_accessibility` with explicit operator authorization. It is registered in the static world-tool router, not dynamically imported from model text.

Every cue is derived from current source text. Timings are estimated from word counts, not synchronized with rendered speech. Stage order and ending obligations are checked against canonical quest and canon proof. All text is escaped for Markdown/HTML and WebVTT, control characters are refused, output is bounded to 65536 bytes, and output SHA-256 plus source leases are returned for deterministic replay. The existing playable HTML5 story remains the interactive editing surface; this edition is a separate accessibility handoff, not a replacement game runtime.

Focused tests: `python -m pytest -q tests/test_studio_story_accessibility.py`. Source is WIP until these and exact-head CI succeed.
