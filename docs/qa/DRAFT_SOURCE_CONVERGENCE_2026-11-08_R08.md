# R08: Safe reconciliation of held #5079 source without whole-branch merge

**Review-only / Draft / No merge or release authority.** Parent #5089 SHA `6bbc98c43b38f12c2e8967ed4f6a2098308d2c17`; sibling source #5079 head `328df45682e745dbe5f796a27aacfc04cfeeddb3`. Original quarantine branches, sibling #5079, parent #5081 and upstream #5074 remain intact. Do not count source grafts as approvals.

Reused ten immutable Git-blob source paths (two reviewed changes, eight additive); retained the current #5081 250,000-file finite inventory cap, studio ZIP schema policy, verified native digest fixture and single unique questflow test path rather than overwriting their newer versions. Reconciled the #5079 finite scanner boundary test to assert 250,000 exactly and its source-only workflow to the real test paths, with no bypass or skipped security steps. The model loader uses POSIX descriptor-relative no-follow traversal, hardlink rejection, re-open identity and checked SHA; no model weights activated.

Selected exact source objects:
- added `docs/qa/DRAFT_19_RECONCILIATION_2026-11-08.md` — `225b65205472175c6ff681b2f02542bfa6ddbaa4`
- added `docs/qa/PR_5081_SOURCE_OVERLAP_RECONCILIATION_2026-11-08.md` — `9490223afe0cc64aa91630ef1ecff51a3b98275d`
- added `machine/draft19_reconciliation.json` — `5c429e894a196af0acefff773acb82199a77c42c`
- added `scripts/check_draft19_reconciliation.py` — `289440deb6167c44f2f283cf6ac32a098e544040`
- modified `skeleton/local_ai/model_loader.py` — `c6ee1da4d1b395b9ef95fb464c2c20218e1adc9f`
- added `skeleton/testing/dialogue_sessions_v1/__init__.py` — `8afb2969080744b6386787795bb723e92f641ef6`
- added `skeleton/testing/questflows_v1/__init__.py` — `89749da97d67bb0fd068d34c761b789a1f9d922e`
- modified `skeleton/testing/test_app_offline_mixed_game_library_continuity.py` — `ba8c52e889990ee57c4ece12550e2586e2ce0cd0`
- added `skeleton/testing/test_local_ai_gguf_custody.py` — `0933dbc5364a6fb776c594c18bdd74134357bcc4`
- added `tests/test_draft19_reconciliation.py` — `48bf2c9b2a82d28c35dcaf5ee320407fb0f0a38d`

Explicit retained conflicts: `.machine/repository.toml` (250,000 vs older 150,000 finite cap); `backend/core/lazy_registry.py` (already identical to reviewed #5081); `skeleton/app/offline_delivery_archive.py` (independent schema/byte-budget adjudication); `skeleton/testing/test_ai_next_model.py` (already fixed with its own forged-digest regression); `skeleton/testing/test_app_offline_delivery_archive.py` (alternative helper not in canonical #5081); `skeleton/testing/test_app_offline_archive_schema_parity.py` and `skeleton/testing/test_repo_machine_inventory_budget.py` (identical to #5081). No whole-file replacement of these conflicts.

Run final-head focused GGUF tests, exact source ancestry, 19-held-source ledger guards, finite inventory, archive/signed continuity tests and all required Merge Readiness, Backend Quality, Malware, Secrets, Dependency Review, Sealed Context Guard, App Foundation E2E and independent device qualification. Skipped, pending and ancestor-only checks are not accepted.
