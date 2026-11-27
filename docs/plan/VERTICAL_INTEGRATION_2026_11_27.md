# Vertical integration checkpoint — 2026-11-27

This checkpoint continues the existing Jeeves → Dragon → Skeleton delivery.
It is a current-source decision record, not a production, model-quality or
competitive-superiority certificate. The accompanying
[JSON inventory](VERTICAL_INTEGRATION_2026_11_27.json) records exact heads,
observed workflow metadata and the selected job-level checks.

## Current base and previous delivery

The new checkout is based on main
`4ac4c585f666f79862508a9bd70db56bb63f40cf` (#6001). It contains 230
first-parent commits since November 20. Review current owners before adapting
older branches: many archive restorations, runtime changes and dependency
updates have landed since the previous delivery.

Previous delivery [#5709](https://github.com/Apeloff1/Skeleton/pull/5709)
was merged on November 23 at 05:33:06 UTC, with merge commit
`f3525a1eef58d70cd5519790c5e5ca79a42a132a` and final head
`155ed9ee1cc12ffec5aba1d7b18f59a4095a63b5`. Its old branch is not an open
integration destination. Preserve the earlier November 19 ledger as its own
immutable historical cutoff; do not rewrite its 181-PR inventory as current.

## Open PR decisions

The paginated open inventory returned four PRs at this checkpoint:

| PR | Exact head | Disposition |
| --- | --- | --- |
| [#6003](https://github.com/Apeloff1/Skeleton/pull/6003), draft | `613876240382cbb487290c8bdf1a930aa7764abb` | Review the narrow optional-PyTorch admission and checkpoint-preservation fix. It adds real subprocess/scoring tests, not trained-model quality evidence. Verify its current-source behavior and canonical mapping before adaptation. |
| [#6002](https://github.com/Apeloff1/Skeleton/pull/6002) | `d106a4f8472d26f3177bf8f4f5d8bd66f94e7553` | Reference-only module-object test patch for spool telemetry. No new end-user capability; retain independent work. |
| [#5933](https://github.com/Apeloff1/Skeleton/pull/5933) | `7f4d90aaba9ad811b4065a62cc8a703ceb9d9ca4` | Do not replay wholesale. It deletes real archive expiry, permission, privacy and injection regressions, replacing callable fixtures with constants. Preserve the real tests; review any import correction individually. |
| [#5932](https://github.com/Apeloff1/Skeleton/pull/5932) | `dedef6ba77fc5f131f04453e197ddb5a4b604b84` | Overlapping predecessor to #5933 with the same regression-erasing stub. Preserve current authority and real regression coverage. |

No donor merge, release or remote state change was performed by this audit.

## Product reconciliation findings

The local model-builder HTTP bridge was restored through #5373/#5894. Current
`offline_http.py` composes `LocalGameBuilder` and exposes the documented four
`/v1/game-builds` routes. Its `offline_web.py` client still has no corresponding
builder controls or API calls. Restore the missing client through those owners
instead of creating another compiler or service.

The current guided-Jeeves source still keys Studio handoff by the artifact
digest and captures authentication before explicit stored-token hydration.
The previous unpushed origin-key and cold-start fixes require reconciliation.
The typed Forge parameter component directory is also absent from current main;
its recovery must preserve the current authoring preview/save authority.

Three Dragon regression modules were replaced with placeholder stubs by
#5925/#5929/#5931/#5936. The stubs did not exercise Atlas, treasury or archive
permissions, and changed callable fixtures into incompatible constants. This
increment restores the last meaningful versions of those three targeted test
modules, without changing production policy or replacing the whole tree.
The JSON records each original commit and restored file identity. All **42
restored tests passed** against the actual canonical source using
`PYTHONPATH=. python -m unittest -q tests.test_ai_webcrawler_dragon_atlas
tests.test_ai_webcrawler_dragon_treasury
tests.test_ai_webcrawler_dragon_archive_grant`.

## What current CI establishes

The four exact-head all-event queries returned 30 workflow runs within their
reported 100-item page limits. Job details were inspected for four identified
runs, totaling 20 jobs; this is deliberately not every job of every run.

On #6003, the successful App Foundation E2E workflow ran only the Playwright
installation-retry contract. The actual stack/browser E2E and Apple M1 jobs
were skipped. Its Backend Quality run failed the vertical backend selector and
frontend client steps. A workflow title or aggregate success therefore cannot
be treated as current user-journey, device or model acceptance.

#6002's full Node regression stopped at the node_modules patch step; Python
regression stopped at Ruff before pytest. #5933's Dragon Hoarder run failed
canonical capture and temporal qualification while its animation source job
passed. Retain these distinctions when evaluating any subsequent source fix.

The ongoing implementation must report its own exact source, relevant test
execution and actual user journeys. This inventory claims no inference,
physical device, original asset, production-release or competitor qualification.
