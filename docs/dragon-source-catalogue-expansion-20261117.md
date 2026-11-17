# Dragon source catalogue: tenfold acquisition and hundredfold admission

The previous packaged catalogue at 3ba6603356e248a8e16772b4a7e1c8880f356651 contained 382 distinct candidate roots, 357 hostnames and ten source families. The November 17 expansion retained all of those roots and added 3,494 public repository roots returned by GitHub repository search, followed by 18 independently located publisher/dataset entry points. At 479dcbd2a039203f8bd6669fdfb92e23f4d666fc the packaged count is 3,894 roots over 366 hosts. This is >10x candidate roots, NOT 10x domains, not 10x independently licensed publishers, and not a claim of inspected repository contents or successful network acquisition. No fixture root is packaged.

## Acquisition provenance

All repository queries used public, non-archived results; exact returned browser URLs and full repository names were retained, with case-insensitive repository identity deduplication. Tags are search-topic metadata, not facts established from scraping project contents. Public visibility does not establish a reuse licence or crawler consent. Counts are after existing-root and cross-query deduplication.

| Commit | Search topics | Added | Total |
|---|---|---:|---:|
| e7c8a44efc93a8bb461616b1c1913da554749f9a | game-engine, godot, unity, unreal-engine, minecraft-mod, game-modding | 533 | 915 |
| c6fe566c73014fb60ea4b31a1223de92342aedfe | skyrim, fallout, fivem, world-of-warcraft, ffxiv, eve-online | 531 | 1446 |
| da646260179c9cd910071b45c97baa4801395a37 | game-assets, pixel-art, procedural-generation, level-editor, emulator, rom-hacking | 543 | 1989 |
| f4febf688c314df22a5a737bf128f5b508dc07bb | runescape, path-of-exile, terraria, factorio, stardew-valley, rimworld | 539 | 2528 |
| 185211da9e8634f4263c6b63480bfa54aab9dee5 | game-data, gaming-api, game-ai, game-tools, game-development, gamedev | 329 | 2857 |
| fce31ee3176afcd9c721e70d48eaa39236649805 | renpy, rpg-maker, open-source-game, game-server, doom, gameboy | 524 | 3381 |
| 7e0de69d14ecc614994a5aefeef2963571ae7e0d | nes, zelda, speedrunning, dota2, league-of-legends, game-jam | 495 | 3876 |
| 479dcbd2a039203f8bd6669fdfb92e23f4d666fc | publisher portals, archival data, assets and APIs | 18 | 3894 |

Independent data-entry references are recorded in the catalogue itself. These include Preserve Games, EFGAMP, Old Games Gallery, Sorcade, Game Census, CodeSights, GameDB, Zenodo OSSGameBench and Hugging Face dataset cards. Some datasets or connectors have restricted access or terms. Discovery is not authorization to acquire their underlying datasets.

## Second expansion

Baseline 100x = 38,200 actual distinct candidate URLs. A full tenfold increase on the delivered 3,894 would be 38,940. Neither populated count has been attained. The canonical registry now admits up to 65,536 candidates and at most 32 MiB of JSON. Large single-host catalogues use exact longest-path-prefix lookup and bounded ranking: 256 global candidates plus up to 128 best distinct-origin representatives. The registry is still loaded in memory and exact scoring still visits eligible rows. This is not a benchmark of production throughput or an unbounded global corpus.

The offline bulk expansion module accepts explicit URL metadata from a separately reviewed publisher export; it does not fetch sites, read credentials or derive URLs from guessed IDs. Normalize the approved export as JSONL, one object with exactly name, url, family, kind, tags. Use the existing catalogue vocabulary. Pin both byte digests and provide the publisher HTTPS locator and operator metadata-rights reference.

```sh
python -m skeleton.ai.webcrawler.source_catalogue_bulk \
  --base skeleton/ai/webcrawler/catalogues/dragon_source_catalogue.v1.json \
  --export reviewed-export.jsonl \
  --base-sha256 EXPECTED_BASE_SHA256 \
  --export-sha256 EXPECTED_EXPORT_SHA256 \
  --publisher APPROVED_PUBLISHER_HTTPS_LOCATOR \
  --rights-reference APPROVED_METADATA_RIGHTS_REFERENCE \
  --minimum 38940 \
  --output candidate-catalogue.json \
  --receipt candidate-receipt.json
```

Use an actual trusted export for each publisher; do not count catalogue item records unless they contain real eligible candidate locators. The module performs strict schema and bounded stream parsing, no silent replacement of existing metadata, duplicate/conflict accounting, digest validation, no-clobber output publication and minimum-populated-count admission. Output and receipt are intentionally separate; a crash after the output but before the receipt requires review of the orphan output and a new output name. Only a matching receipt plus independently reviewed bytes may be considered for packaging. The existing canonical implementation digest binds packaged catalogue and ranking code, so upgrading incompatible checkpoints remains a separate migration/consent decision.

## Qualification and holds

New fixture tests exercise an actual registry of at least 38,200 synthetic rows (or ten times the packaged count), ranking and host diversity, collision handling, malicious locator rejection, digest failures and no-replace publication. Fixture locators must never enter the packaged registry or be reported as live sources. The exact-head workflow is wired to run these tests; this is not yet an executed pass receipt. Existing consent, robots, local/private address, source-use, archive/revocation and dispatch policy are unchanged.

No new runtime root, external credentials, automatic external acquisition, actual source access validation, license determination, independent device qualification, release or merge authority. Further growth is expected through reviewed source exports and the existing grant-current graph, not fabricated seed URLs.
