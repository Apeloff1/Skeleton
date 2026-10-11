# Dragon acquisition: ninth sequential batch

Checked 2026-10-11. Registry range [256, 288), sorted by source ID, begins `sources-002.jsonl`. The implementation remains on PR #3605. This is a data-only acquisition change, not runtime deployment or canonical admission.

## Counts

| Result | Count |
|---|---:|
| Newly checked | 32 |
| Fetched representations | 22 |
| Retrieval failures | 10 |
| Repository metadata | 10 |
| Target pages | 8 |
| Metadata shells | 4 |
| Blocked from admission | 32 |
| Distilled | 0 |
| Approved | 0 |
| Exact license/rights files fetched | 7 |
| Auxiliary identity/rights files fetched | 17 |

Every candidate remains blocked pending source-specific policy, rights, custody, source review and Wiki/HOAG gates.

## Scoped findings

- Two catalog GitHub URLs resolved to different canonical repository paths: `thestonefox/VRTK` to `ExtendRealityLtd/VRTK`, and `r-lyeh/FWK` to `r-lyeh/v1`. These are recorded as identity transitions, not ownership, abandonment or rights conclusions. The captured FWK/v1 README also points development to v3.
- Standalone MIT license files were captured for VRTK, thekla_atlas, QOI, Squid and 2048-cli; Filament supplied Apache-2.0; awesome-pascal supplied CC0-1.0 for its list. Linked projects, dependencies, samples, assets, trademarks and patents remain separate.
- threeHungryMice and FWK/v1 supplied no standalone license in the attempted root paths. ShaderTutorials states CC BY 4.0 in its README but supplied no standalone root license file. Public visibility and README claims were not treated as unrestricted permission.
- The 2048-cli repository is archived. That status was not treated as public-domain, abandonment, inactive-IP or legal-clearance evidence.
- Microsoft recommends on-device Unity profiling and separating CPU/GPU bottlenecks; its returned page also displayed authorization warnings. The observation remains unreviewed and platform-specific.
- QOI's README contains compression/throughput comparisons, but its linked benchmark was not reproduced. No external experiment or training occurred.
- Blender-Models exposes mixed per-item licenses, including noncommercial and share-alike variants. No model was downloaded, and catalog labels were not treated as chain-of-title proof.
- Mesh2Motion states CC0 availability for its own source animations and no LLM processing of uploads, while separately crediting third-party animations. Exact repositories, files and third-party terms still require verification.
- The BOLA page itself calls the license historical and recommends CC0 or the Unlicense. No legal-clearance inference was made.
- Three video candidates produced two retrieval failures and one playlist metadata shell. No video, audio or transcript was downloaded.
- Candidate partition: three video and 29 web/provider records; zero separately enumerated edition records. Worldwide coverage remains unknown.

## Almanac and learning state

The candidates mapped to 23 actual catalog-header almanacs. Source evidence, AI hypotheses, measured findings, negative results, prototype lessons and product lessons remain distinct. Reference observations are unreviewed and none entered canonical almanacs. AI-generated descendants and catalog aliases add no independent support.

No external training or experiment was performed. No reviewed-note retrieval pack was rebuilt because there are no eligible new canonical notes; sparse routing weights remain distinct from trained neural parameters.

## Validation and continuation

Registry shard SHA-256 matched the manifest, cursor continuity reached 288 unique source IDs, JSON/count consistency was checked, and 17 selected-revision files received SHA-256 plus locally reproduced Git-object identities. The connector did not expose API blob SHAs for comparison, and selected commit-search revisions are not represented as proven branch heads. Commit ancestry and remote readback remain publication gates. Runtime tests are not rerun because runtime code did not change.

Next first-pass cursor: 288 / 4,405 (6.538%). Approval coverage: 0 / 4,405. Worldwide game/video/edition/provider coverage remains unknown.
