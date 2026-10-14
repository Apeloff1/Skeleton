# Dragon Mother Glean Matrix — analysis and Wiki/HOAG verification handoff

**Authored:** 2026-10-12 (UTC)  **Source lineage:** 248 curated candidate URLs, existing canonical Dragon policy/fetch/extract stages.

## Implemented in this milestone

The Dragon's acquired source observations now pass through a deterministic, source-exact **Glean Matrix** before a separate independent Wiki/HOAG decision. The new `DragonTechnicalGlean` adapter uses the existing `DragonSourceCaptures`, `SequentialAlmanacWorker`, `ReviewedKnowledgeStore`, `DragonWisdomPyramid`, and role-signing `DragonWisdomAuthority`; it creates no new fake knowledge authority.

### Nine source lenses

| Lens | Task relevance questions (not presumed facts) |
| --- | --- |
| Mechanics | NPC behavior, player movement, collision and quest interaction |
| Implementation | API, build, compiler, memory/register and algorithm constraints |
| Performance | Frame timing, GPU/CPU costs, bandwidth and latency |
| Compatibility | Hardware generations, platform ports and version differences |
| Failure | Error cases, bugs, unsafe behavior, exceptions and overflows |
| Validation | Evidence quality, benchmark requirements, reproducibility |
| Rights | Licenses, copyright, trademarks and provenance permission |
| Production | Editor, asset, packaging, releases and toolchain integration |
| Uncertainty | Hedging, experimental results, unknowns and cautious wording |

Each reading consists of an original quote of at most 240 characters, exact start/end indices, a content-bound SHA-256 digest, deterministic lens trigger terms, and unanswered research questions. The output is **hypothesis support material only**: confidence is `not_assessed`, stance `unreviewed`, facts `fact_checked=false`, verified independence `0`.

### Peer comparisons and invalidation

An operator may request up to eight owner-scoped peer sources. The adapter compares the latest observed content identity, overlaps in relevant technical concepts, possible negation differences and same-host/source duplication. It marks any discrepancy as `lexical_tension_hint` and every peer as `independence=not_proven`; it never certifies contradictions or independent agreement by keyword matching.

Changes in captured source text invalidate the previous analysis and require a fresh extract/analyze/review cycle. A subsequent unchanged observation of the same content **does not erase valid reviewed work or create additional XP**. Reading sources from other owners is forbidden.

### Canonical workflow continuity

The fully-integrated sequential path is now:

```text
Policy (actual robots/terms/reference-use permission)
  -> Fetch (socket-bound transport and content hash)
  -> Extract (verbatim, verifiable evidence spans)
  -> Analyze (atomic, digest-bound Glean Matrix; never auto-truth)
  -> Canonical Review (only with existing accepted independent Wiki evidence)
  -> Separate HOAG approval and adversarial weight sandbox (not executed here)
```

`complete_analyze` writes the whole bounded analysis packet **inside** the existing trusted stage-3 almanac receipt, in the same transaction that advances the job to canonical review. A crash cannot leave a falsely completed detached analysis ledger. Its packet is capped at 12,000 bytes (inside the existing 16,384-byte evidence limit).

`handoff` verifies the current full stage receipt lineage, captured revision, current reviewed knowledge snapshot, and exact analysis hash, then produces a compact review packet. Quotes are withheld unless the trusted operator explicitly requests them.

`complete_canonical_review` requires a real **live canonical-review claim**, current reviewed document whose source text hash matches the capture, conflict-free current KnowledgeBrief with two distinct independent source groups, an existing **accepted Wiki verdict**, and a valid role-specific, cryptographically signed reviewer grant. It verifies that the Wiki verdict's signed evidence, independent reviewer, original source citation and review timestamp all match. The canonical review stage is never completed from unreviewed crawler output alone.

**Crucial limits:** Reviewer grant signing is only trustworthy if external principal identity and affiliation are actually authenticated. The connector/integration does not claim to have done external identity verification. The code does not generate a Wiki grant, forge reviewer independence, acquire source rights, promote HOAG memory, train a neural model, or deploy a background process.

### Trusted local operator interface

```sh
python -m skeleton.ai.game_builder.dragon_technical_source_cli glean-preview \
  --database /approved/dragon.sqlite --owner studio \
  --source-id source-<64hex> --capture-digest <64hex> \
  --trusted-local-operator

python -m skeleton.ai.game_builder.dragon_technical_source_cli glean-handoff \
  --database /approved/dragon.sqlite --owner studio \
  --source-id source-<64hex> --trusted-local-operator
```

Optional `--peer-source-id` arguments let the operator compare up to eight registered current sources. `--include-captured-text` on handoff exposes short exact quoted evidence to an authorized operator; the default omits quote bytes. Neither command starts network I/O.

### Validation

Add `tests/test_dragon_technical_source_analysis.py` to Dragon AI Verification. The suite covers immutable exact-source lensing, deterministic repeated previews, authenticated tenant isolation, historical revision invalidation, unchanged-update stability, adversarial peer tension, replay/tampering resistance, atomic stage-3 handoff, positive independently reviewed canonical closure, forged Wiki proof, expired reviewer evidence, and single-source insufficiency. A CI success must be observed on the exact commit before it is called verified.

**Next operations milestone:** Deploy actual consented acquisition workers with durable cross-process reservations, bounded robots-delay scheduling and a rights-review queue. Independently review curated sources, cross-check contradictory technical claims, and benchmark model improvements on original-game output before any shadow-weight or permanent-weight transition. This code pass does not assert that any of the 248 entries has been downloaded or accepted.
