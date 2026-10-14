# Dragon companion — three first-class hatchlings and mother research
**Timestamp:** 2026-10-12 UTC
**Change target:** `Apeloff1/Skeleton` / `feat/dragon-wisdom-review-20261010` / PR #3605.

## Corrected architecture — all THREE hatchlings

The companion Dragon has one mother and **three** genuinely distinct child research roles. The previous cross-media milestone integrated video and update specialists while relegating the original article hatchling to existing background infrastructure. This upgrade removes that asymmetry:

| Hatchling | Actual job | Evidence custody | What it does NOT do |
| --- | --- | --- | --- |
| **Article** | Governed public web-article intake, exact snippets, technical search lenses and review packets | `DragonSourceCaptures` and new `DragonArticleHatchling` | Cannot approve facts or train a model |
| **Video** | Timecoded, independently permission-attested transcript reference evidence | `DragonVideoTranscriptLedger` | Cannot download video or fabricate captions |
| **Updates** | Genuine changed-source revision detection with original/new exact spans | `DragonSourceDeltaLedger` | Cannot create changes from unchanged recrawls |

Each child keeps an **individual provenance identity**. The signed companion nest remains the only authority for actual growth and progress. Growth still requires reviewed lawful evidence with genuine five-minute-idle/background worker admission. Staging research alone does not produce XP, hatchling levels, training, shadow weights or accepted Wiki claims.

## Milestone A — Article hatchling promoted to first-class specialist

New `DragonArticleHatchling` is an owner-scoped, bounded, **read-only** specialist interface over the existing policy-governed article ingestion ledger. It exposes material article revisions, exact text spans, cryptographic quote digests, topical technical lenses, observation timestamps, curated source family and a visible change-history explanation in parentheses.

**Important data-loss fix:** A later *unchanged* HTTP reobservation must not erase an earlier material revision's review packet. The new article specialist selects the most recent genuinely new/changed capture while separately reporting the latest observation. Both digests remain visible; it counts unchanged revisits since the material capture. It never guesses whether an external reviewer approved the finding, and it hides literal quotes in the default read-only preview.

Trusted local read-only commands:
```sh
python -m skeleton.ai.game_builder.dragon_technical_source_cli article-review \
 --database /approved/studio.sqlite --owner studio \
 --source-id source-<64hex> --trusted-local-operator

python -m skeleton.ai.game_builder.dragon_technical_source_cli article-census \
 --database /approved/studio.sqlite --owner studio \
 --limit 64 --trusted-local-operator
```
Add `--include-captured-text` only when an explicitly authorized reviewer needs short exact passages. Use `--after-source source-<64hex>` for bounded census paging.

## Milestone B — Actual three-child companion status

`DragonThreeHatchlingCoordinator` now reports **article, video and updates**, in that stable order, for individually registered owner-bound source IDs. Each lane displays current evidence-readiness, exact receipt digest, observation time and its specific (improvement) note. When supplied the canonical signed `DragonNestStore`, the coordinator also reads **actual** mother stage/level and each child's stage, level and accepted evidence count.

A signed nest without unlocked children reports them as **locked**. No child is silently omitted; missing transcript rights or missing material revisions are shown as distinct pending states. The status view cannot start a crawler, allocate RAM, or change signed nest records.

The article and updates roles may refer to the **same real article source**. In that situation the report explicitly gives a distinct source count of **two** when a video source is present—three roles do not mean three independent publishers.

## Milestone C — Three-way mother Dragon gleaning

`DragonThreeHatchlingCoordinator.mother_review` fuses three exact evidence classes in one bounded, deterministic research hypothesis:

1. A specific timecoded cue from the video hatchling.
2. An exact article passage from the article hatchling.
3. A newly changed, source-exact span from the updates hatchling.

The mother proposes up to 12 traceable hypotheses only where all **three** share meaningful task vocabulary. Each includes full source IDs, custody receipts, offsets/timecodes, exact original snippets and questions about versions, meaning, independence and potential invalidation. There is **no claimed agreement**, independent corroboration, model learning or automatic weight promotion. Wiki/HOAG remains responsible for source independence, conflicting evidence and proven model improvement.

If even one child has no valid staged review input, the mother returns `awaiting_three_reviewable_lanes` instead of inventing a missing component. The underlying two-lane view is preserved for compatibility, but the corrected companion-facing view is the new three-child interface.

## Verification and timestamped improvements

The `tests/test_dragon_specialist_evidence.py` suite extends offline, real-global-resource fixture coverage to all three hatchlings, including: article quotes preserved through unchanged recrawls; bounded owner-isolated article census; tamper detection; actual three-lane mother observations and receipt matching; stable game XP despite pending evidence; missing-lane abstention; and deterministic three-way proposals. The older workflow's discoverable `tests/test_ai_dragon_source_safety.py` adds a fail-closed three-child import test. The focused Dragon Source Safety job now compiles the article and three-child coordinator modules explicitly.

The test cases are **authored but not yet independently proven passing** in GitHub Actions. No live crawling, permission issuance, video download, hidden background execution or neural model promotion occurred in this milestone.

**2026-10-12 UTC change history:**
- (Article hatchling now has the same first-class review/status interface as videos and updates.)
- (Unchanged article revisits retain the last genuine material evidence.)
- (Mother recognizes all three specialized research roles and signed game progress.)
- (New cross-media research proposals carry three separate exact evidence receipts.)
- (Research clues are kept separate from source independence, XP, Wiki/HOAG approval and model weights.)

## Production next steps

Implement a trusted application interface that displays the three-child status and allows explicitly permissioned reviewer inspection, connect the licensed transcript-ingestion provider, and run the exact-head Python safety suite. Deploy only after independently verified rights and OS-level supervision are available.
