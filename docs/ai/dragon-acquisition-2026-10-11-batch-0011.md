# Dragon acquisition: eleventh sequential batch

Checked 2026-10-11. Registry range [320, 352), sorted by source ID, continues `sources-002.jsonl`. The implementation remains on PR #3605 rather than current main. This is a data-only acquisition change, not runtime deployment or canonical admission.

## Counts

| Result | Count |
|---|---:|
| Newly checked | 32 |
| Fetched representations | 23 |
| Retrieval failures or target mismatches | 9 |
| Repository metadata | 13 |
| Target pages | 6 |
| Metadata shells | 4 |
| Blocked from admission | 32 |
| Distilled | 0 |
| Approved | 0 |
| Exact license/rights files fetched | 10 |
| Auxiliary identity/rights files fetched | 21 |

Every candidate remains blocked pending source-specific policy, rights, custody, source review and Wiki/HOAG gates.

## Scoped findings

- openage explicitly separates its free engine clone from proprietary game assets: it does not ship those assets and requires a supported original game. This is useful architecture/rights-separation evidence, not permission to use the games, assets or trademarks.
- Veldrid's README says public updates stopped in February 2023, but authorized commit search returned a 2026 commit. The contradiction is retained for maintainer/status review; neither statement proves abandonment.
- Three Nebula, FXGL, Dialogic and WebGL2Samples supplied MIT license bodies. Veldrid supplied MIT; los-cocos/cocos supplied a BSD-style license. These code grants do not automatically cover examples, third-party components, media, brands or patents.
- WebGL2Samples' license file enumerates third-party code, so provenance remains component-specific. Its browser compatibility table is dated 2017 and was not retested.
- Tungsten supplied a zlib-style license with a third-party inventory; Awesome F# supplied CC0 for its list; incbin supplied the Unlicense; Polycode supplied MIT. Those terms do not transfer to linked projects, input files, dependencies or third-party assets. Mega Girl, openage and the Unity game-jam project yielded no standalone root license through attempted common paths.
- The Mega Girl repository describes Mega Man inspiration and third-party credits; the Jekyll-and-Hyde jam repository names a literary basis. Neither relationship was treated as legal clearance.
- HacknPlan's 2015 practitioner article recommends outcome-oriented task decomposition, iterative milestones and reduced context switching. No causal productivity claim was admitted.
- Alex Charlton's 2016 article describes matrix-threshold ordered dithering suitable for fragment shaders. It remains an unreplicated author account, not a benchmark or peer-reviewed result.
- Holiday Liu's 80 Level feature recommends reference study, perspective-first blocking, feedback-intent analysis and workflow experimentation. It remains practitioner guidance.
- Ableton, Catlike Coding and hofk.de returned educational/index pages. Linked lessons, examples, songs, code and archives remain individually gated.
- The PNGoo ZIP was not downloaded: the authorized text channel rejected `application/zip`. YouTube, X, Google Sheets, Hextris and several legacy targets remained unavailable, throttled or shell-only.
- Candidate partition: four video candidates and 28 web/provider records; zero separately enumerated edition records. Worldwide game, video, edition and provider coverage remains unknown.

## Almanac and learning state

The batch maps to 23 actual catalog-header almanacs. Source evidence, AI hypotheses, measured findings, negative results, prototype lessons and product lessons remain distinct. Reference observations are unreviewed and none entered canonical almanacs. Catalogs, mirrors and AI-generated descendants add no independent support.

No external training or experiment was performed. No reviewed-note retrieval pack was rebuilt because there are no eligible new canonical notes; sparse routing weights remain distinct from trained neural parameters.

## Validation and continuation

Registry shard SHA-256 matched its manifest, cursor continuity reached 352 unique source IDs, and JSON/count consistency was checked. 21 selected-revision files received SHA-256 and reproduced Git-object identities; 21 matched the connector's Git blob SHA and 0 mismatched. Commit-search revisions are not represented as independently proven branch heads. Runtime tests were not rerun because runtime code did not change.

Next first-pass cursor: 352 / 4,405 (7.991%). Approval coverage: 0 / 4,405. Worldwide game/video/edition/provider coverage remains unknown.
