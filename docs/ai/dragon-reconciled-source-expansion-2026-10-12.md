# Dragon source research: reconciled eleven-batch evidence chain

**Date:** 2026-10-12  
**Scope:** Game creator research discovery only; no source-use, copying, training or license authority.

## Quantified raw discovery

| Property | Recorded count |
| --- | ---: |
| Original pinned source registry | 4,405 |
| Historical raw URL expansion (batches 0020–0023) | 1,033 |
| Additional raw discoveries in reconciled batches 0031–0037 | 5,113 |
| Recorded raw lead total | **10,551** |
| 10× planning target | 44,050 |
| Raw discovery coverage | **23.95%** |

These are **raw URL leads**, not approved or independently verified websites, media, code, games, publications or model-training examples. Canonical URL collisions are calculated separately by the importer. No amount of discovering links can authorize a model-weight promotion.

## Recorded source provenance

The reconciled expansion records links from immutable Git SHA and README-blob identities at five public development catalogs: `FronkonGames/Awesome-Gamedev`, `stevinz/awesome-game-engine-dev`, `dawdle-deer/awesome-learn-gamedev`, `Caerind/AwesomeCppGameDev` and `hzoo/awesome-gametalks`. It also carries forward source URL evidence from the independent acquisition references contained in batch 0024. Each URL retains its raw SHA-256 identity, pinned catalog identity, observed heading lineage where available, and source line location.

Batch 0024 was recorded using an acquisition-specific format without the required historical parent chain. Batch 0030 referred to batches 0025–0029, which are not present on the current branch. **Neither orphaned document is accepted as part of the sequential import chain.** Their individual URL observations were rechecked against the available pinned catalog references, deduplicated, and represented in the new, independent batches 0031–0037. The excluded documents remain available for audit; their apparent total is never used as import authority.

The valid ordered evidence sequence is `0020, 0021, 0022, 0023, 0031, 0032, 0033, 0034, 0035, 0036, 0037`. Each new document declares the complete expected preceding path sequence and exact cumulative raw count. The chain is checked **before** metadata admission begins.

## Operating the source queue

Verify the complete discovery evidence, including URL identities and rights-denying assertions, with:

```sh
python -m skeleton.ai.game_builder.dragon_almanac_cli discovery-verify \
  --database dragon.sqlite --owner studio --trusted-local-operator
```

After reviewing the reported counts, a trusted local operator can import the metadata-only inventory:

```sh
python -m skeleton.ai.game_builder.dragon_almanac_cli import-reconciled \
  --database dragon.sqlite --owner studio --trusted-local-operator
```

This does not fetch any linked page or promote any distilled knowledge. Every new source enters the policy stage with unknown rights, unknown independence and `training_authorized=false`. Subsequent work must pass applicable crawl permissions, SSRF/network checks, source authenticity, rights review, analysis, adversarial knowledge review, Wiki/HOAG checks and independent evidence before any downstream training decision.

The `mission-index`, `mission-scout`, `mission-portfolio` and `campaign-record` commands can then operate over the policy-stage inventory. They remain explicitly proposal-only.

## Known limits

Raw README parsing is heuristic. A pinned README is proof of bytes at one repository revision, **not** proof that a linked destination is accessible, up-to-date, licensed, independent or suitable for imitation. A video shell is not a transcript, a repository link is not a legal right to reuse copyrighted code, and a game ROM is not an approved homebrew asset. Links may contain mirrors, incidental badges, obsolete pages or dead destinations. The next meaningful milestone is policy-admitted crawling and evidence-backed topic distillation, not inflating source counts.
