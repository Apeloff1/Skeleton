# Dragon source catalogue: second acquisition wave

Start: `879cb6b1db71bd1a129482b258b03ad8f2a91947`, 12,523 distinct candidate URLs over 6,133 hostnames. Target remains 389,400 actual distinct URLs. This wave adds 7,655 candidates across six package shards; 20,178 distinct candidate URLs over 7,577 hostnames at the acquisition head `30dca4602132f7269b6e602c0756197fc26fc171`. Counts are candidate locators, not fetched content, verified licences, independent publishers or crawl grants.

## Acquisition receipt

All imported titles/links are public catalogue observations or exact repository search results. Local generic tags are advisory; no publisher descriptions, assets or credentials are retained. Deduplicated against all preceding package parts, including case-insensitive URL identity comparison. This conservative comparison may exclude distinct case-sensitive paths. Listings are not content-level or availability reviews.

| Shard | Publisher/source | Input blob or query / acquisition commit | Added |
|---|---|---|---:|
| 0005 | https://github.com/EllisonLeao/magictools | 7f10e6c5e2420bf68c5700aff7bdff0130203b68 | 278 |
| 0005 | https://github.com/Calinou/awesome-godot | 50c4ef53ecca4bed21f8cb8955e0ceb9a4414e2f | 288 |
| 0005 | https://github.com/bobeff/open-source-games | 0a54e0898d52ffa31f83f843b66aee458c5a49b8 | 208 |
| 0005 | https://github.com/leereilly/games | 6c1dd472d6c789fcf8cfc0d721f7538c2ead1158 | 288 |
| 0005 | https://github.com/Kavex/GameDev-Resources | 685f424e92697d654837d05fe98c30ff8c5011a5 | 58 |
| 0006 | GitHub public repository queries | ffc221e3d1336bc793f7a720194246ccd70def1c | 555 |
| 0007 | https://github.com/Th0rgal/awesome-modding | f6ced2a3662149d16d92dc8e967f835ad6dcc3b7 | 320 |
| 0007 | https://github.com/killop/anything_about_game | b254994ab5d818d814397d081b4513b43528483a | 2667 |
| 0007 | https://github.com/raizam/gamedev_libraries | 46f744768839b8d27f591053d50fba02e4126883 | 114 |
| 0007 | https://github.com/insthync/awesome-unity3d | fcf69a3273de0492e340723d624116e48594a742 | 468 |
| 0007 | https://github.com/xpfasd/awesome-game-wiki | 8f8151eee96e367162948ec379c723199739c82c | 110 |
| 0007 | https://github.com/mikeroyal/Unreal-Engine-Guide | aea8783ecb5e8ee29f443ccbcb6e56a0197dfc7a | 866 |
| 0008 | https://github.com/Calinou/awesome-gamedev | 560680be5964c57ca6e0e471bba74f0a2c2330af | 5 |
| 0008 | https://github.com/skywind3000/awesome-gamedev | 5e6cf21b765dbe1cfacfdd323ba10e49a6e4b0c8 | 11 |
| 0008 | https://github.com/InfiniBrains/Awesome-GameDev-Resources | 67195d3609d09681acb8eb6b6a2a646855d43bfd | 6 |
| 0008 | https://github.com/datamllab/awesome-game-ai | a94f19ac8deaec10d222b0e9ca16fe1bb2aabc55 | 20 |
| 0008 | https://github.com/Eurekaleo/awesome-ai-for-games | d869a8108c6b751ec5f1ae3ba8fe9ce70fb42647 | 1 |
| 0008 | https://github.com/bytecauldron/awesome-level-design | fca31e3df5d7c818dd58a91308700164edd37fab | 35 |
| 0008 | https://github.com/luisdnsantos/awesome-computer-graphics | a69a917082760757649c9ba3d429fb4a550c97d4 | 7 |
| 0009 | https://github.com/IndieWikiBuddy/indie-wiki-buddy-data (dist/v1/all-data.json, wiki.gg destination subset) | b68fae8e3ceaccd3b414c1b5133c016d9929bc94 | 260 |
| 0009 | https://github.com/leomaurodesenv/game-datasets | 0eed50905f837dc11ff4e473b98cecb214a11f1f | 179 |
| 0009 | https://github.com/gbdev/awesome-gbdev | 29de0c90a682ebb6bc48fb77f775b9b06cc882bc | 277 |
| 0009 | https://github.com/mikeroyal/Game-Development-Guide | d792202bbaee003d49edddab8ec6bf80611f0c85 | 3 |
| 0009 | https://github.com/lebrancconvas/awesome-game-console-development | 5336a0edca25f93e1d9f315aab633f1f0c4744ed | 44 |
| 0009 | https://github.com/Dvergar/awesome-haxe-gamedev | ab99cff65413400f64ca1ede9e8d132ad0853b5e | 105 |
| 0010 | GitHub public repository queries | 30dca4602132f7269b6e602c0756197fc26fc171 | 482 |

Repository query receipts: shard 0006 used minecraft-plugin (80), factorio-mod (68), kerbal-space-program (93), openra (41), renpy (0), phaser (87), threejs game (93), roblox-studio (93). Shard 0010 used game-engine page 3 (69), godot page 3 (66), game-server page 2 (83), game-modding page 3 (91), game-jam page 2 (90), game-design page 1 (83). Non-public/archived results, existing locators and obvious undesired names were excluded. The screening is not an exhaustive content classification.

## Import campaigns

The new offline tool `python -m skeleton.ai.webcrawler.source_catalogue_campaign --help` composes the existing normalization and index builder. The operator supplies a UTF-8 JSON plan with schema `skeleton.dragon.source-import-campaign.v1`, minimum_sources (389400 for this target), base_sha256 (SHA256 of packaged_catalogue_bytes()), and exports. Each export has id, relative file, sha256, existing normalizer mode, publisher HTTPS locator, and rights_reference. The input root and output work directory must be disjoint; use operator-controlled non-concurrently-written directories. The plan is itself pinned by SHA256. Resume only in a directory pinned to the same plan; completed normalized outputs and published generation are validated against receipts. Interrupted partial publication is held without clobber. Receipts do not independently authenticate the publisher or prove rights; use trusted local input custody and review. No network or automatic activation.

Additional acquisition leads (not counted, no bulk download performed here): the explicitly licensed Global Game Jam dataset (https://huggingface.co/datasets/FronkonGames/Global-Game-Jam-Dataset, published as MIT, 31,918 rows at inspection, explicit name/url columns); Nobody Clicked browser-game census (https://nobodyclicked.com/census, published 9,056 historical sightings at inspection, explicit title/url); The Game Census (https://thegamecensus.com/data, CC BY 4.0 downloadable games-index CSV and documented canonical slug mapping). Independently review publisher terms, extract only source locators and preserve attribution and removal requests. Provider row counts are not distinct acquired candidate counts, particularly when historical links or overlap are present.

## Qualification

At the preceding exact head 879cb6b1db71bd1a129482b258b03ad8f2a91947, [source atlas run 43995393814](https://github.com/Apeloff1/Skeleton/actions/runs/43995393814) passed both jobs, including physical synthetic index job 133746081211: 389,400 synthetic candidates; 352,735,232 database bytes; 39.441s build; 0.279s verified open; 0.590s candidate lookup; seven tests passed. This is CI-runner evidence only, NOT actual publisher acquisitions, production-device throughput or new-head qualification. New package shards modify implementation identity; existing incompatible checkpoints require requalification/migration. Existing review, merge, network, device and release holds remain; no permissions expanded.
