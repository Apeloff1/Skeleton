# Dragon industry almanacs: production knowledge and learning cascade

Implementation date: 2026-10-10. Implementation author: Codex. Independent verification: not performed. Production deployment: not complete.

## What exists now

The repository includes a real source-discovery snapshot, topic indexes within the canonical ReviewedKnowledgeStore database, project-learning lineage, versioned entity records, a sequential receipt workflow, compact sparse retrieval packs, an executable CLI, and a reproducible original experiment. It does not contain all games or all videos, a fully approved web corpus, a deployed network executor for this new workflow, or a newly trained general game-building model.

Measured local bootstrap: 4,405 normalized source URLs, 1,359 hostnames, 631 video candidates, 3,774 other web candidates, eight retrieved discovery catalogs, 35 integrity-checked shards, 3,695 topic-almanac nodes and 4,405 pending acquisition jobs. Hostnames are not independent publisher counts. Almanac nodes include organizational parents and six knowledge sections; node count is not a count of populated or validated subject areas.

The initial corpus is strongly biased toward development resources and English-language community lists. It is an acquisition starting point. It is not representative of every regional game tradition, every platform, historical release, commercial production practice, player group or genre. Availability and rights were not checked individually for all 4,405 URLs.

## The almanac unit

Every header path has a deterministic, owner-scoped topic identity and parent relationship. Identically named headers in different contexts remain separate. A topic can accumulate many versions and cross-references without copying the underlying source into every child. Membership reaches ancestors so broader topic views remain useful. New catalog headers create their own almanacs automatically; the same API accepts additional research and project headers.

Each semantic topic has six sections: source evidence, machine findings, prototype lessons, product lessons, contradictions and rights. The initial industry/niche hierarchy creates these sections before evidence arrives, and explicitly leaves them empty. A machine finding is a separate record, not an overwrite of an official document.

An operational almanac should answer: What is the claim? Under which game build, hardware, player population, language, task and rules? Who observed it? Where are the exact spans or timecodes? What supports it? What contradicts it? Which evidence shares an origin? What experiment would falsify it? What can be reused, cited or trained on? Which prototypes and products depend on it? What must be withdrawn if evidence changes?

The implemented project-learning record captures project identity, exact artifact digest, topic, lifecycle stage, finding kind, statement, method, limitations, evidence digests, parent learning digests and exact canonical source/revision/note references. The embedding runtime must authenticate the submitting worker and the evidence artifacts. A caller-supplied digest is an identity, not independent verification that an experiment happened.

## Industry research domains

| Domain | Knowledge headers |
|---|---|
| design | core loops; player agency; difficulty curves; systems interaction; progression; failure recovery |
| narrative | world rules; character motivation; branch consistency; dialogue; environmental storytelling; adaptation analysis |
| level design | spatial grammar; encounter pacing; navigation; teaching; gating; procedural validation |
| player research | experimental design; sampling; telemetry; qualitative interviews; causal inference; uncertainty |
| accessibility | motor access; visual access; hearing access; cognitive access; assistive devices; inclusive playtesting |
| graphics | rendering pipelines; lighting; materials; visibility; temporal stability; performance budgets |
| animation | locomotion; blending; inverse kinematics; facial systems; procedural motion; readability |
| physics | collision; rigid bodies; soft bodies; fluids; determinism; simulation limits |
| game ai | navigation; planning; behavior selection; opponent modeling; coordination; debugging |
| audio | music systems; spatial sound; mixing; dialogue playback; latency; audio accessibility |
| input | device mapping; latency; buffering; gesture recognition; haptics; alternative controls |
| user interface | information hierarchy; menus; HUD; onboarding; error recovery; controller navigation |
| networking | replication; prediction; rollback; matchmaking; latency compensation; disconnect recovery |
| online operations | hosting; capacity; observability; incident recovery; regional routing; service retirement |
| security | untrusted content; save integrity; anti-cheat; authentication; supply chain; privacy |
| engine architecture | scene graphs; entity systems; scheduling; serialization; hot reload; plugin boundaries |
| tools | editors; import pipelines; asset validation; profiling; build automation; creator workflows |
| compilers | language runtime; optimization; target ABI; linking; debug symbols; reproducible builds |
| storage | save formats; transactions; migrations; cloud conflicts; compression; recovery |
| hardware | CPU behavior; GPU behavior; memory; storage bandwidth; display timing; power and thermals |
| historical platforms | native toolchains; cartridge constraints; disc media; controllers; regional variants; hardware verification |
| homebrew | original code; asset provenance; SDK provenance; device deployment; community documentation; distribution rights |
| porting | behavioral fidelity; target adaptation; input translation; rendering translation; save portability; cross-platform validation |
| quality assurance | unit behavior; integration; property testing; fuzzing; long-duration testing; release regression |
| production | scoping; dependencies; milestones; budgeting; outsourcing; change management |
| business | pricing; distribution; market research; unit economics; forecast uncertainty; postlaunch support |
| monetization | purchase flows; time costs; reward transparency; regional restrictions; player wellbeing; refund behavior |
| community | moderation; creator tools; user content; competitive rules; dispute handling; community preservation |
| localization | text systems; translation; fonts; bidirectional layout; cultural review; regional testing |
| preservation | version history; source archives; media provenance; emulation context; rights chains; missing works |
| criticism | review methods; reviewer expertise; disclosures; satire context; cross-review disagreement; correction history |
| video analysis | creator identity; episode identity; timecodes; editing context; observed mechanics; transcript rights |
| legal | copyright; patent claims; trademarks; trade secrets; contracts; territorial distribution |
| research integrity | primary evidence; source dependence; replication; negative results; retractions; synthetic-data lineage |
| machine learning | dataset rights; deduplication; train-test separation; model evaluation; quantization; rollback |
| delivery | packaging; installation; patching; certification; support; retirement and archival export |

The preceding niche catalog adds 84 niches and 252 mechanic entries across 21 families. These are complementary axes: a bullet-hell game can use almanacs for input latency, accessibility, projectile simulation, progression, criticism, localization, rights and delivery. A historical handheld port needs platform-specific evidence rather than a visual-style label.

## Source discovery and selection

The shipped snapshot records URLs actually extracted from retrieved catalogs. No domains were generated to reach a numerical target. The catalog snapshots are identified by retrieved Git blob SHA and SHA-256 of the returned text. Each URL has catalog ID, source line and header lineage. Source shards have byte hashes, row counts and a whole-registry digest.

| Retrieved discovery catalog | Git blob |
|---|---|
| https://github.com/stevinz/awesome-game-engine-dev/blob/main/README.md | `0cb679e26cd9901fe0254b0501eba1d5b7bbbc29` |
| https://github.com/FronkonGames/Awesome-Gamedev/blob/main/README.md | `22d1ea9ee7692d8bde120a568c842730b57f08e0` |
| https://github.com/hzoo/awesome-gametalks/blob/master/README.md | `4270593f0271ba1b5725bfdd90b76f02bb37c6f9` |
| https://github.com/skywind3000/awesome-gamedev/blob/master/README.md | `5e6cf21b765dbe1cfacfdd323ba10e49a6e4b0c8` |
| https://github.com/leereilly/games/blob/master/README.md | `6c1dd472d6c789fcf8cfc0d721f7538c2ead1158` |
| https://github.com/RyanNielson/awesome-unity/blob/master/README.md | `7394989fa763d76b572ea8acf2d8c75e3f35007f` |
| https://github.com/Calinou/awesome-godot/blob/master/README.md | `e07646729442a33df33d9ab3072ecb77fd7e8f75` |
| https://github.com/dawdle-deer/awesome-learn-gamedev/blob/main/README.md | `ea02900f953b417abd2e71286e7f51cf640baf02` |

These catalogs are discovery sources, not eight independent studies validating their contents. Their licenses do not automatically apply to linked resources. URL normalization removes fragments and tracking parameters but deliberately preserves content-defining query parameters and path case. It does not assert that two different URLs have different authors or evidence. Later content and ownership clustering must detect mirrors, syndication, copied tutorials and repeated datasets.

A six-URL spot check through web retrieval returned pages for Godot pipeline compilation, Unity TextMeshPro, MDN WebGL, Khronos glTF and a Game Developer shadow-mapping article; the selected YouTube URL returned a retrieval error. This is not a statistically representative availability estimate and does not convert the registry into an approved corpus. A direct local request to the Godot sitemap returned HTTP 403; no access-control bypass was attempted.

The first expansion pass should stratify acquisition by source type and missing coverage: official engine and platform manuals; developer postmortems; reproducible papers and benchmarks; independently assessed critics; long-form gameplay; homebrew documentation; catalogs and preservation metadata; primary rights records; regional communities. Popularity and directory inclusion are discovery signals, not truth scores.

## Reviews, video and cultural evidence

Retain the 15 existing acquisition classes: reviewer assessments, game reviews, Let's Plays, AVGN, Nostalgia Critic, blogs, news, engagement analysis, homebrew, abandonware-labelled material, unlicensed releases, closed studios, title catalogs, mechanics and patent watches.

Reviewer assessment concerns expertise, methods, first-hand access, game version, platform, review-copy conditions, conflicts, sponsorship, corrections and independent criticism. It must not be represented as academic peer review unless it actually underwent that process. Record aesthetic disagreements rather than forcing consensus. A reviewer may be reliable about one platform and unfamiliar with another.

Video identity must distinguish creator/channel, upload ID, episode, compilation, mirror, language, subtitles, edited version and capture time. Segment observations by timecode and document cuts, staging, mods, device and player skill. A comedy performance does not establish population-level difficulty. A full-season compilation and its individual episodes are not automatically independent evidence. Transcript access is distinct from authorization to download audiovisual media or train on it.

AVGN and Nostalgia Critic remain explicitly requested sources. Check official creator identity and game relevance; do not invent coverage where no relevant episode exists. News engagement needs a measurement window, exposure denominator where available, platform definition, sampling limits and bot/promotion caveats. Attention is not a validated measure of quality or purchase intent.

## Game, video and industry entity catalogs

The implemented entity index supports games, videos, editions, studios, platforms and patents, with provider-scoped IDs, append-only revisions, parent digests and paginated current views. A repeated import of identical metadata is idempotent. A remake, remaster, port, regional edition, rerelease and DLC must not be collapsed solely because titles resemble one another.

Full provider adapters remain acquisition work. Candidate interfaces include Wikidata structured entities, authenticated IGDB game and edition endpoints, publisher catalogs, official platform records, preservation catalogs and authorized YouTube metadata endpoints. Wikidata's structured namespaces have a CC0 policy; that does not extend to every webpage linked from an entity. IGDB access has its own authentication and usage rules. YouTube metadata access has quotas and policies and is not an unrestricted audiovisual download license.

An honest completeness report needs a defined universe: provider snapshot, date cutoff, platforms, territories, languages, release categories, cancelled prototypes and homebrew inclusion. Maintain observed counts, provider cursors, deleted/private records, unresolved identity collisions, excluded categories, last successful page and known gaps. The worldwide denominator stays unknown until a defensible reference universe exists. No finite scrape can certify all web knowledge or every game/video ever made.

## Machine-derived knowledge cascade

The lifecycle is source research -> hypothesis -> original prototype -> instrumented experiment -> independent review -> product experiment -> post-delivery evaluation. Every stage can contribute its own almanac findings. Parent learning digests preserve which hypotheses and prototypes influenced a product. Negative findings are retained because they prevent repeatedly attempting a failed technique.

A finding starts as an AI hypothesis, source synthesis, measured experiment or negative result. All four begin unreviewed. Repeating or rephrasing a finding adds zero independent external support. Current source dependencies are checked when findings are displayed; changed or retracted evidence marks downstream learning stale, including inherited dependencies.

An AI result can augment or challenge official guidance when it has an exact scoped claim, reproducible method, raw evidence, an appropriate baseline, uncertainty and independent checking. The official source remains authoritative about its declared specification; a reproducible implementation counterexample can expose a bug or undocumented boundary. Neither source prestige nor AI confidence settles the conflict automatically.

Protect the feedback loop against circular evidence: keep original observations, independent replication and generated hypotheses distinct; split training/evaluation by project lineage; preserve external holdouts; retain minority and failure cases; track model/version/seed; record selection bias; and prevent the same synthetic family from counting as multiple independent confirmations. Published research on recursive synthetic-data training motivates these controls but does not prove that every form of synthetic-data use causes collapse.

## Original experiment executed in this change

`dragon_almanac_experiment.py` implements a seeded four-neighbor grid-search comparison. The checked-in raw evidence contains all 160 runs, generator settings, grid hashes, path costs, node-expansion counts and train/holdout labels. Uniform-cost and A* search returned matching shortest-path costs in all runs, including agreement on unreachable targets. Exactly 100 grids were reachable.

Across this synthetic workload, uniform-cost search expanded 41,859 nodes and A* expanded 32,664. This is a node-expansion observation, not a wall-clock speedup, player-experience result or new algorithm discovery. The workload is one generator and one implementation, without independent replication.

A least-squares model was trained on 128 runs to predict A* expansion cost from free-cell count. On 32 held-out seeds, mean absolute error was approximately 106.17 nodes, versus 140.13 for a constant predictor derived from the training set. That result is local to this distribution. Model coefficients and raw rows are retained; the finding is unreviewed, and it does not grant permanent memory or product approval.

## Sequential distillation workflow

The implemented persistent workflow processes one active job per owner. It uses expiring random lease tokens, conditional completion, three-attempt blocking and stage priority so a claimed source progresses sequentially before another pending source begins. A crashed worker can be replaced after expiry; its old token cannot complete the reclaimed job. Blocked sources do not indefinitely prevent other sources from advancing.

Stages are policy -> fetch -> extract -> analyze -> canonical review. Policy receipts bind the exact source/input/output and require current robots, terms, reference-use and SSRF decisions. Fetch receipts require a successful checked response, bounded byte count and rechecked redirects. Extraction records parser and span-map identities. Analysis explicitly marks machine claims unreviewed. Final admission requires the exact source URL, source body digest and current revision already admitted by ReviewedKnowledgeStore.

The workflow validates receipts from an authenticated executor; it does not itself fetch HTTP, authenticate signatures, assess licenses, invoke providers or run a hidden daemon. Runtime HTTP acquisition must use the existing crawler and its DNS/redirect/robots/resource controls. Existing recrawl and revision mechanisms remain the owners of freshness after admission. Wiki and HOAG remain the permanent-memory approval path.

Scheduled assistant continuation is a separate operational channel: it can inspect the source registry, acquire bounded batches through authorized tools and preserve progress in the repository. It must not be confused with deployment of a standalone Dragon worker or a guarantee that every scheduled run will succeed.

## Compression and fast use

The implemented pack compiler creates sparse integer term postings over current canonical reviewed notes and compresses the payload. Packs retain source/revision/note identity, scoped statements, stance, dependence group, confidence and evidence spans. Every retrieval verifies the source root and checks selected statements and citations against canonical notes. A changed source invalidates the pack. Contradictions cannot be hidden by editing only the compressed representation.

These are lexical retrieval weights, not trained neural parameters. They support selective knowledge loading without claiming that compression has taught the underlying model a new capability. Performance must include decompression, evidence revalidation, cold-cache and warm-cache conditions, relevant consumer hardware, memory consumption and retrieval quality. No universal latency claim is made here.

The later neural lane should use the existing DatasetRights, DatasetRevision, DistillationRun, CandidateWeights, evaluation and promotion machinery. Admit only explicitly permitted training material; deduplicate by lineage; split by project family; train a versioned adapter or other approved model; evaluate held-out tasks, memorization, contamination, factuality, capability regressions and hardware cost; then use the existing signed promotion/rollback path. Creating a summary or zip file is not neural distillation. Permission for reference analysis is not automatically training permission.

## Game-production use

Use the almanacs to form a creative brief from abstract mechanics, audience needs and measured constraints. Produce independent code, art, audio, narrative and interfaces; record where each contribution came from. Select a target-system capability envelope before promising native output. Keep game behavior, visual style and hardware implementation as separate adaptation decisions.

A prototype should produce compile/build receipts, deterministic replay traces, gameplay metrics, accessibility findings, asset provenance and negative results. A product should additionally produce compatibility evidence, installation/patch/recovery tests, localization checks, user research, content and privacy review, rights assessment, and postlaunch monitoring. Learning from a successful prototype does not remove the need to evaluate its new target, genre or audience.

Legal review must consider copyright expression, substantial similarity where applicable, trademarks and trade dress, patents and claims by territory, contracts and SDK terms, asset and music rights, performers/voices, publicity/privacy and distribution rules. Homebrew is a development category, not blanket legal clearance. An inactive studio or abandonware label does not itself terminate rights. Patent status can change through events including reinstatement; news is a discovery signal while primary records support status review. No formulaic avoidance pattern can guarantee absence of legal disputes in every jurisdiction.

## Controls, economics and recovery

Hard limits are explicit: source registry up to 100,000 URLs, topic paths up to 16 headers, owner topic and learning budgets, bounded learning references and ancestry walks, entity revision limits, three worker attempts, bounded stage receipts, and a 32 MB uncompressed retrieval-pack ceiling. Current limits are operational caps, not claims of industry-scale throughput. Partition owners/scopes and benchmark before increasing them.

Local SQLite indexes reuse the canonical library connection. They provide transactions and scoped identities; they are not replicated cloud storage or cryptographic actor authentication. Hashes detect accidental or local content mismatch but are not signatures. The runtime must authenticate actors, anchor important receipts externally, manage backup/restore, encrypt private data where required and preserve deletion/revocation obligations.

Operators can bootstrap, inspect queue/topic status and execute the original experiment through the CLI. The current application adapter does not add a new provider, service, runtime root or persistent knowledge authority. Production integration must attach existing workers and resources rather than construct parallel authority.

## Commands

```sh
python -m skeleton.ai.game_builder.dragon_almanac_cli bootstrap --database dragon.sqlite --owner gaming --trusted-local-operator
python -m skeleton.ai.game_builder.dragon_almanac_cli status --database dragon.sqlite --owner gaming --trusted-local-operator
python -m skeleton.ai.game_builder.dragon_almanac_cli experiment --database dragon.sqlite --owner gaming --trusted-local-operator --now 1791647564 --output original-grid-evidence.json
```

`--trusted-local-operator` acknowledges the local authenticated boundary; it is not a replacement for network identity checks. Do not expose the CLI as an unauthenticated endpoint.

## L00–L13 implementation and remaining integration

| Layer | Delivered or explicit remaining boundary |
|---|---|
| L00 | Scope, source categories, definitions and measured counts |
| L01 | Existing game-builder and canonical library ownership |
| L02 | Immutable learning records, bounded identifiers, deterministic hashes |
| L03 | Derived topics, memberships and versioned entity records |
| L04 | Catalog ingestion, source provenance and shard integrity |
| L05 | Sequential stage receipts, fenced leases and retry blocking |
| L06 | Owner isolation and authenticated-caller boundaries |
| L07 | Source-root revalidation and inherited dependency freshness |
| L08 | Sparse retrieval packs and retained contradictions |
| L09 | Actual original experiment and held-out learned predictor |
| L10 | CLI bootstrap/status/experiment and reviewable JSON |
| L11 | Adversarial tests, corruption checks and failure recovery |
| L12 | CI integration; production network executor remains unattached |
| L13 | Resource limits, rollback implications and explicit deployment gaps |

Rollback: disable scheduled continuation if necessary, stop attached workers before migration, retain canonical evidence, and remove/rebuild derived almanac indexes and packs. No canonical source or rights record is deleted by this adapter. Source discovery data can be reimported idempotently from the hashed shards.

## Acceptance and truthful progress

Implemented locally: source-discovery snapshot; automatic topic hierarchy; project-learning lineage; entity revision storage; sequential receipt workflow; compact reviewed-note retrieval; original experiment; CLI and tests. Required validators still report the existing stale VOL-000 implementation-notes failure and the provider-bootstrap timeout. Those are unresolved, not passing gates.

Remaining: individual source availability and policy review at corpus scale; actual licensed content acquisition; reviewer assessment; entity-provider adapters and full snapshots; authenticated deployment of the network/analysis workers; broad independent empirical studies; production hardware performance evaluation; neural training on an approved corpus; Wiki/HOAG approvals; and completed game products. Never mark these complete from a count of URLs, folders, summaries, tests or proposals.

## Primary references and methodological evidence

- IETF RFC 9309, Robots Exclusion Protocol: https://www.rfc-editor.org/info/rfc9309/ — crawler access-control conventions and handling, not a copyright license.
- U.S. Copyright Office AI initiative and Part 3 training report: https://www.copyright.gov/ai/ — primary discussion of copyright questions around training; not a universal clearance determination.
- Shumailov et al., Nature (2024): https://www.nature.com/articles/s41586-024-07566-y — research on recursive generated-data training. Consult the linked correction as part of review: https://www.nature.com/articles/s41586-025-08905-3.
- Gerstgrasser et al. (2024): https://arxiv.org/abs/2404.01413 — examines accumulation of real and synthetic data rather than assuming complete replacement. This complements, rather than erases, the need to test the actual training regime.
- Wikidata copyright policy: https://www.wikidata.org/wiki/Wikidata:Copyright — structured-data licensing scope.
- IGDB API documentation: https://api-docs.igdb.com/ — provider-specific metadata interface and authentication.
- YouTube Data API search reference: https://developers.google.com/youtube/v3/docs/search/list — metadata discovery interface and request controls.
- Microsoft XAG 108: https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/108 and Game Accessibility Guidelines: https://gameaccessibilityguidelines.com/full-list/ — complementary accessibility guidance, not proof of a particular product's outcomes.
- U.S. Copyright Office Games: https://www.copyright.gov/register/tx-games.html and USPTO MPEP 2590: https://www.uspto.gov/web/offices/pac/mpep/s2590.html — relevant rights distinctions and reinstatement considerations.

All external references were inspected or retrieved during the 2026-10-10 research session. Their scope must be retained when deriving claims. This design is an authored synthesis; it is not itself a peer-reviewed validation of the production system.
