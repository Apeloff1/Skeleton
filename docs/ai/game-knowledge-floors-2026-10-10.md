# Game knowledge foundation, successor library and original products

Implementation increment, 2026-10-10. Three executable adapters extend the
existing game-builder owner. No new runtime root, database, provider or crawler
service is created. This is not a completed global game dataset or an active
background monitoring deployment.

## First floor: research and attributed knowledge

`game_research_foundation.py` defines fifteen distillation targets and generates
title-specific discovery queries with required context. The targets include
independent assessments of reviewers, game criticism, Let's Plays, Angry Video
Game Nerd/Cinemassacre, Nostalgia Critic/Channel Awesome, blogs, news, news
engagement, homebrew, historically labelled abandonware, unlicensed releases,
closed studios/inactive IP, title catalogs, mechanics, and patent records.

Named creators are discovery targets, not automatically endorsed authorities.
Nostalgia Critic material needs an explicit medium and game-relevance review;
film commentary is not evidence about a game's actual implementation. AVGN and
other comedy reviews retain satire/staging context. No creator impersonation,
account following, subscription, download or rehosting occurs.

Two independently controlled peer-assessment groups must document domain
expertise, correction practices, sponsorship disclosure and traceable evidence.
Shared review documents and group relationships form transitive dependency
clusters. Self-review, stale assessments and unresolved adverse criteria block
readiness. This is reviewer-quality assessment, not academic peer review.
The embedding authenticated process must verify the peer identities, ownership
claims and review documents; metadata alone is not authentication.

Each distilled observation binds its exact source-body digest, reviewed URL,
short source span and citation locator to the existing rights ledger. It stores
an attributed observation and required context rather than silently elevating
opinion to fact. Raw source bodies are not emitted. A Let's Play needs version,
platform, timecode, edits, mods, player-skill and input context; it is not an
unbiased player study. News-engagement requires its measurement window,
denominator, platform, sampling, automation bias and privacy context. Counts
and virality never become truth or proof of audience-wide preference.

The prior `assess_custodied_promotion` empirical gate remains separate. A
factual generalization still needs its independent empirical records,
calibration and analysis review. Observations here grant neither training,
memory promotion nor expressive reuse. Collection permission, content reuse,
model training and release remain distinct decisions.

Inspect targets locally:

```sh
python -m skeleton.ai.game_builder.game_research_foundation --title "Original homebrew"
```

## Dataset acquisition and live-watch preparation

`game_ip_watch.py` accepts bounded, explicitly registered subjects and custodied
reports. Each subject binds a title, right type, territory and registration or
contract identifier. Each report includes the same identity, source URL,
record locator, body/custody digests, reported status/expiry and observation
time. The module retains report history and identifies changed bodies or
interpretations. It never guesses an expiration date from a title's age.

At least one recognized primary register and two independent source clusters
must cross-check a status. Common issuing authorities, publisher groups, hosts
and copied bodies collapse into one group. News is a corroboration/alert source,
not a substitute for a primary register. Disagreement, unknown status, missing
or future expiry basis, stale observations, lapse and potential reinstatement
produce explicit investigation reasons. Cross-checked reports still require
legal review and confer no reuse or release authority.

Initial primary-register mappings cover selected US, EPO and Norwegian
authorities. EPO-wide records do not stand in for a country's post-grant status.
Other registers and court filing systems need reviewed onboarding; no wildcard
government-domain acceptance is used. A recognized hostname does not prove
that a supplied interpretation is correct: authenticated ingestion must verify
the cited registration, document and exact legal-event meaning.

Inspect a custodied JSON batch without network I/O:

```sh
python -m skeleton.ai.game_builder.game_ip_watch --input watch.json \
  --as-of 1791638400 --trusted-local-operator
```

The JSON has `subjects` and `reports` arrays matching the typed records. Input
is limited to 2 MB, 1,000 subjects and 10,000 reports. The output supplies refresh
reasons and next-check times to the existing crawler owner. Actual scheduled
dispatch, authenticated register sessions, retries, persistent subscriptions,
and notification delivery are not implemented by this projection.

"All titles/mechanics/patents" remains a coverage objective. There is no known
complete authoritative catalog for this combined universe. Future acquisition
must track per-source/territory/platform/time-window coverage, aliases and
editions, record counts, provenance, acquisition permission, failures, cursors
and refresh receipts. A source enumeration is never evidence that coverage is
complete. No game ROM, BIOS, leaked SDK or proprietary code is acquired here.

## Second floor and roof

`successor_blueprints.py` composes two explicit, independently authored design
briefs: a stepping-stone project and its new product. It consumes source IDs
with reference permission through the existing rights ledger. Each blueprint
records original asset/code plans and authorship evidence. The roof binds the
exact parent digest and specifies a different era, genre, story, visual style,
time setting and gameplay. These changes satisfy the requested creative axes;
they do not measure semantic novelty or establish legal independence.

Both artifacts receive their own canonical jurisdiction/target legal review
matrix and originality coverage for characters, plot structure, dialogue,
visuals, music, levels, code, branding and mechanic patent claims. Parent
clearance never transfers to a changed child. Missing/stale/blocked reviews and
existing high-risk similarity findings block review readiness. Even a fully
review-ready pair has `build_state=not_built` and no release authority.

This deliberately implements positive original-design controls rather than a
formula for disguising protected expression. Renaming characters, rearranging
a copied storyline or moving a game to a different era cannot guarantee lawful
reuse. Similarity detection, reviewed authorship and jurisdiction-specific
rights assessment remain necessary. Distinct research IDs are not proof of
source independence; factual inputs must first satisfy empirical promotion.

## Primary references and legal scope

- US Copyright Office, Games: abstract game ideas/methods and protectable
  expression are different. This does not remove patent or trademark concerns.
  https://www.copyright.gov/register/tx-games.html
- US Copyright Office, duration and derivative works: ownership/inactivity is
  not replaced by a release-year heuristic, and new additions do not erase
  rights in existing material.
  https://www.copyright.gov/what-is-copyright/
  https://www.copyright.gov/circs/circ14.pdf
- USPTO: maintenance-fee lapse and reinstatement require careful distinction.
  https://www.uspto.gov/patents/maintain
- EPO: national registers are the source for current post-grant status;
  supplementary legal-status feeds may contain gaps or delays.
  https://register.epo.org/help?lng=en&topic=eplegalstatus
  https://www.epo.org/en/searching-for-patents/legal/register
- Cinemassacre identifies its game/movie review and comedy work. This supports
  target identity, not factual endorsement or content acquisition permission.
  https://cinemassacre.com/category/gaming/

Sources checked 2026-10-10. These are methodological and legal background
references, not game-specific clearance. Closed studios, homebrew, abandonware,
unlicensed products and inactive IP are research labels, never rights grants.

## L00–L13 and remaining acceptance

L00–L02: existing game-builder/rights/legal owners and typed bounded adapters.
L03–L04: explicit authenticated ingestion, reference rights, conservative
source-quality checks and artifact-specific review. L05–L07: read-only
projections, source/parent digests, immutable returned history, unknown/stale/
conflicting status retained. Existing custody owners remain responsible for
durable history and authentic review evidence. L08: explicit reasons, citations,
coverage boundaries and content digests. L09: bounded input/output and no model
or network calls. L10: category coverage, provenance/citation attacks,
dependency clustering, replay conflicts, expiry, ownership and parent/child
review isolation. L11–L12: additive modules with no migration; disable consumers
to roll back without weakening existing release gates. L13: global dataset
acquisition, live dispatch, authentic document parsing, deep semantic
originality evaluation and compiled product generation remain open.

Signed: Codex, 2026-10-10. This sign-off covers this implementation increment;
it does not close the complete first floor, second floor or roof.

Validation: 95 tests and 2 subtests passed across the foundation, existing wisdom
integration, knowledge/rights bridge and empirical promotion suites. Both new
operator CLIs were exercised as real subprocesses. Architecture, construction,
capability interfaces and enterprise-superiority schema checks passed. The
implementation-notes check still reports the existing stale
`VOL-000.existing_evidence` field; provider bootstrap is reported separately.
