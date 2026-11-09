# Dragon acquisition: fifth sequential batch

Checked 2026-10-11. Registry range [128, 160), sorted by source ID; this is the first bounded pass through `sources-001.jsonl`. The implementation remains on PR #3605. This is a data-only acquisition change, not runtime deployment or canonical admission.

## Counts

| Result | Count |
|---|---:|
| Newly checked | 32 |
| Fetched representations | 21 |
| Retrieval/redirect failures | 11 |
| Repository metadata | 12 |
| Target pages | 7 |
| Metadata shells | 2 |
| Blocked from admission | 32 |
| Distilled | 0 |
| Approved | 0 |
| Exact license/rights files fetched | 9 |
| Exact auxiliary identity/rights files fetched | 21 |

Every candidate remains blocked pending source-specific policy, rights, custody, source review and Wiki/HOAG gates.

## Scoped findings

- The DOOM release pairs GPL-2.0 source with an explicit statement that original game data is still required; engine-code visibility does not transfer asset, trademark or data rights.
- Project Hawkthorne has mixed scope: MIT software, noncommercial Creative Commons original assets and separately licensed other assets. Manic Digger likewise inventories public-domain software language alongside separately licensed sound and dependencies.
- Bandai Namco Research labels both motion datasets CC BY-NC 4.0 and the Blender visualization scripts MIT. No dataset was downloaded or trained on; noncommercial terms are not product-training authorization.
- The game-market benchmarking article distinguishes hard data from projections and labels revenue formulas/guesses as estimates. This remains practitioner guidance, not empirical validation.
- RPG wealth, C# networking, Unity codebase tours, tilemap export, WebGL2 curriculum and Ren'Py platform claims were captured as narrow, attributable, unreviewed observations.
- The BlockoS/blob entry is a game-specific catalog false positive: its metadata describes a connected-component labeling implementation. Three video targets and multiple other pages were unavailable in the authorized retrieval channel.
- Candidate partition: five game, three video and 24 provider/reference records; zero edition records. This does not establish global inventory coverage.

## Almanac and learning state

The candidates mapped to 29 actual catalog-header almanacs. Source evidence, exact rights-file identities and negative retrieval results remain distinct. AI hypotheses, measured findings, prototype lessons and product lessons remain empty. Generated descendants add no independent support.

No external training or experiment was performed. No reviewed-note retrieval pack was rebuilt because there are no eligible new canonical notes; sparse routing weights remain distinct from trained neural parameters.

## Validation and continuation

Registry shard SHA-256, progress continuity, 160 unique source IDs, JSON/count consistency, 21 auxiliary Git blobs, default-branch commit identities, commit ancestry and remote readback are validation targets. Runtime tests are not rerun because runtime code did not change.

Next first-pass cursor: 160 / 4,405 (3.632%). Approval coverage: 0 / 4,405. Worldwide game/video/edition/provider coverage remains unknown.
