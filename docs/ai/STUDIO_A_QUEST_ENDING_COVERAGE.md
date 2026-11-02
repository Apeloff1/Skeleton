# Studio A: canonical quest ending coverage

This vertical proves independent source-replayed authored quest ending paths. It is distinct from the existing softlock audit, which asks whether any selected ending is still possible. The authoring contract uses initial_actions, target_endings, max_states, and max_depth. The CLI scripts/studio_quest_ending_coverage_cli.py supports prompt, strict authoring file, private publish, restore, HTML review, and playable sandbox handoff. The Jeeves static router exposes a read-only typed adapter.

Each witness replays against the canonical quest interpreter with source and initial-session digests. Unexplored branches never count as negative proof. Native engine, external evidence, rights, device and release qualification remain held.

Focused regression: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider tests/test_studio_quest_ending_coverage.py
