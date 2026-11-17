# Dragon source catalogue: hundredfold index expansion

Baseline: 3,894 packaged candidate URLs at 38ac2388b0bdfd6d1b0cfd5a40fa29f59e93d3d8. Requested population target: 389,400 distinct candidate URLs. This wave packages 12,523, not 389,400. The new optional immutable SQLite index admits up to 1,048,576 sources within its file/export/manifest bounds. Capacity is not population, a completed benchmark, or verified source access.

## Acquisition and attribution ledger

Each import retains explicit observed URLs and titles, with locally assigned family and generic tags; no downloaded game assets, publisher descriptions, or credentials. Duplicates against existing catalogue are excluded. Public catalogue listing does not confer crawl or content reuse authorization.

| Source | Accepted new URLs | Git blob / acquisition commit |
| --- | ---: | --- |
| GitHub repository searches (Bevy, MonoGame, libGDX, Pygame, raylib, LÖVE) | 519 | f7b0a52cdadab99c9e70fc17526fd9996c30e271 |
| GitHub repository searches (game engine, Minecraft mod, Godot, Unity, Unreal, game modding) | 517 | 9066eb9cab0c76057e64288d4b140ad658f9dd6e |
| https://github.com/djeada/awesome-open-source-games-list (data/catalogue.json) | 300 | dcb02dd961bb3ed3cff8384c9744adc5bf7ee6d8 |
| https://github.com/GameDev-Toolkit/awesome-GameDev-tool | 943 | b6b4e808435404a2fbcfa45bbe622a7e5aeb9d11 |
| https://github.com/dawdle-deer/awesome-learn-gamedev | 177 | ea02900f953b417abd2e71286e7f51cf640baf02 |
| https://github.com/FronkonGames/Awesome-Gamedev | 8 | 22d1ea9ee7692d8bde120a568c842730b57f08e0 |
| https://github.com/substain/tools-for-gamedev | 203 | 45d99464682b940c7cd948493848af238c435bf9 |
| https://github.com/jjones26/free-and-open-source-game-dev-resources | 38 | 71291906241110f638b1aaa542537872b4b7ff77 |

**Free itch.io games catalog by poli0981 (SkullMute) — https://freeitchgames.win — CC BY 4.0.**
Source: https://github.com/poli0981/free-games-itchio-list/tree/main/data_game .
License: https://creativecommons.org/licenses/by/4.0/ .
Adaptation: retain project URL and title, labeled non-NSFW in the source export; deduplicate and assign local metadata. This is not an independent safety/content or underlying game license assessment.

| game_info shard | Added | Git blob |
| --- | ---: | --- |
| 001 | 481 | 969b2cd67b6c7b3c1842a9bd027f41c6a7738e8f |
| 002 | 497 | 740b1543592adda725016a720c485db4b9686d1d |
| 003 | 444 | 0f05ead1cfae1d5aa209fbe20fc7b77bb6ac3a44 |
| 004 | 499 | 6ad0266ceb4ed443cda796b98d8ecb23bb1b0aea |
| 005 | 499 | 85afaa62ca702b0c08af1403bad59df8efd9d4df |
| 006 | 493 | f7ef61aa85279c85d8269aa9ee326e83a27c4a89 |
| 007 | 494 | 97034f7fa83de048ffce64723f18f24355852d2e |
| 008 | 497 | cf65d4461a94d0ee9fc205a3a1e5a42c9208d01e |
| 009 | 482 | 3d6062435435f97bec295a5b19c021c064a399bf |
| 010 | 428 | ff94dd0f287997ce80da9dfb8ba206562e288764 |
| 011 | 487 | c72a69f721bead8a6eff1b7f798b587c6c9f483b |
| 012 | 489 | 18d3a0a36404d1bc257d7e3a5116885a2c647650 |
| 013 | 134 | fa5ccba3986f011eae1e41b99fd7e48ef7fa0df6 |

Total added 8,629. No invented fixture URL is counted in the shipped population.

## Operator-controlled generation

Normalize reviewed local exports with `python -m skeleton.ai.webcrawler.source_catalogue_normalize --help`. Pin the input SHA256, publisher and rights reference; retain the original receipt and generated JSONL. Assemble the index export objects into a reviewed JSON list and use `python -m skeleton.ai.webcrawler.source_catalogue_index --help`.

Supply the SHA256 of the exact concatenated packaged catalogue bytes (use `packaged_catalogue_bytes()`), reviewed exports, output directory and minimum 389400. A below-minimum build must fail. Install the generated manifest and SQLite database together in an operator-controlled read-only directory and, only after review, select the manifest using SKL_DRAGON_SOURCE_INDEX_MANIFEST. No automatic download, replacement, migration, grant, or deployment. Keep the original exports and normalization receipts alongside the reviewed custody record. Changes to the packaged source/index binding invalidate prior incompatible checkpoint identities; do not bypass requalification.

Proposed additional reviewed inputs, not acquired here: explicit URL exports from Wikidata (official website P856), Game Census (https://thegamecensus.com/data), browser-game census (https://nobodyclicked.com/census), and crosswalk exports (https://github.com/datavizlouis/gnv-starter-kit). Review current publisher terms, provenance, and removal requests before import. A provider database's row count is never a verified source count. No silent ID-to-URL guessing or automated credentialed source acquisition.

## Evidence and holds

Dedicated hundredfold workflow builds, reopens and queries a 389,400-row synthetic fixture; it is stress-test evidence only and does not add real sources. Bounded ranking does not promise exhaustive global recall. The 1,048,576-row ceiling is an implementation limit, not a measured device result. Final-head qualification, physical production scale, access/rights verification, source population and review remain open. Existing robots/consent, transport and release gates are unchanged.
