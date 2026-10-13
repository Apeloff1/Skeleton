# Rival convergence observatory: original games versus competing titles

October 2026. Deliverable in PR #3645, stacked on adversarial learning PR #3643 and game builder PR #3642.

**Terminology:** The internal category **enemy** means a competitor **game title** that credibly converges with an already-documented original game plan. It is not a statement about a developer, a plagiarism accusation, permission to copy expressive elements, or authority to harass or threaten anyone.

## 1. Production objective

Monitor observed rival game mechanics and compare them with the user's original, precommitted game plans. Demand demonstrably better player value, technical quality, accessible gameplay, original story and world character, performance, polish and platform-specific fidelity. Preserve the original game's distinctive authorial voice, unusual mechanics, thematic identity, NPC personalities, lore, atmosphere, art direction and license/rights permissions.

The strategic priority is not a legal determination or a market-fact inference. Every external assertion requires review and provenance. Numbers of files, generated cases, press releases and tests are not proxies for competitive product quality.

## 2. Implemented architecture

| Module | Responsibility | Boundaries |
|---|---|---|
| rival_convergence_observatory.py | Original game plans, competing titles, observed source signals, convergence scoring and hysteresis, benchmarking, delivery gate, SQLite SHA journal | No competitor-game copying; no legal opinion; no automatic release |
| rival_public_monitor.py | Explicit opt-in official Steam News API sampling, bounded URLs, metadata-only records, fixed HTTPS endpoint, no redirects/proxies | Public news cannot certify features or quality |
| rival_delivery_campaign.py | Mandatory six-stage work ladder for every affected quality axis, tasks and prereqs, source-bound outcome reconciliation | Does not claim Jeeves/HOAG/Dragon work was performed |
| rival_watch_cli.py | Local watch, human-reviewed analysis, historical heads, checked delivery signoff | Trusted-reviewer flag assumes external authentication |
| game-rival-observatory.yml | Linux/Windows adversarial and source integrity CI; daily read-only monitored source snapshot | Scheduled workflows activate only after landing on default branch |

The quality axes and protected axes are imported from the existing game-builder forge, not invented independent standards.

## 3. Competition and convergence

1. Register the original game with immutable plan revision SHA, registered-at timestamp, original identity pillars (at least 2), distinctive signature SHA and its concrete planned features (up to 128).
2. Enroll a known competing title, including official source URL. No person or publisher is an "enemy"; only a title can carry the internal competitive priority.
3. Public feeds supply source URL, source digest, publication time and observed time. Curators with authenticated external rights must independently review and tag the specific capability IDs with evidence digests.
4. Preplan competitor behavior is excluded from claims of new postplan convergence. An older game cannot be alleged to have copied a later plan.
5. Collapse evidence repeats and publisher/dependence groups. Default enemy entrance requires **at least 2 original planned features**, **at least 2 independent reviewed source groups** and **at least 55% weighted plan-feature overlap**.
6. Prior documented enemy status can persist with a lower 35% overlap exit threshold only while independent source and capability counts continue to be satisfied.
7. Missing or unreviewed evidence creates WATCH/UNCONFIRMED, not ENEMY. Review receipt digests alone are not cryptographic signatures and must never be represented as independently signed attestations.

A reviewed news/article is not a game feature unless it has an explicit reviewed gameplay claim. Feature similarity is a competitive-priority heuristic, not an originality/plagiarism test.

## 4. What “outdo” actually demands

Only quantitative measurements based on **the same predeclared protocol, canonical quality axis and independent evaluator** may be compared. Samples must number at least 30 per evaluation with linked source evidence. No ranking by random scraped star scores, unverified critic preferences or a self-reported trailer is admitted.

If the rival scores 80/100 on a verified comparable axis, the default mandatory *original-game improvement target* becomes 85/100. If already above this, the system marks DEFEND_VERIFIED_LEAD and requires no regression. If no pairing exists, it commissions a benchmark rather than inventing an improvement. At a rival score above 95, a literal +5 cannot be achieved on a 100-point scale: the order becomes DIFFERENTIATE_AND_CAP with a target capped at 100, original player value and explicit nondeceptive reporting.

Mandatory identity preservation work is always included with verified enemy campaigns. Improving gameplay feel, mechanics, accessibility, performance, NPC agency, plot consequences, art/aesthetics, replayability and player clarity should increase perceived value while remaining a recognizable individual original game.

## 5. Six distinct proof-bearing work stages per relevant quality axis

| Execution request lane | Work required |
|---|---|
| Wiki / independent benchmarks | Study reliable research evidence, licensing and competitor weakness; preregister comparable assessments |
| Jeeves / original design | Produce a new original mechanic implementation and/or quality advancement preserving identity pillars |
| Game Builder / actual production | Implement playable mechanics/content and performance improvements in the real game |
| Adversarial Mirror | Repeatedly break and challenge canonical replay, NPC/story coherence, controls, originality and platform behavior |
| HOAG / player polish | Verify accessibility, understanding, feel, aesthetic consistency, player preference and usability; polish based on evidence |
| Wiki/Rights / external signoff | Verify source rights, independent original gameplay, measured uplift, identity protection and explicit release authorization |

Each machine-actionable task binds order ID, original game project, competitor title, protected signature digest, source report digest, predecessor task, named execution lane, priority and required evidence description. Reconciliation rejects missing tasks, bad evidence, skipped prerequisites, wrong projects and unreviewed receipts.

The lane names describe requested delegated work. They do **not** imply the existing Jeeves/HOAG/Dragon services have already executed those tasks or authenticated their completion.

## 6. Live monitoring and running the CLI

The public watchlist at docs/ai/game_rival_watchlist.json is deliberately configured as:

- schema: skeleton.game_builder.competitor_watch_config.v1
- polling_enabled: false
- titles: []

No specific competing title was supplied and none was fabricated.

When a maintainer independently verifies a legitimate public Steam app and official title, they may add a CompetitorTitle record (title_id, public_name, publisher_id, official_url, steam_app_id), set polling_enabled to true, and run:

    python -m skeleton.ai.game_builder.rival_watch_cli poll --config docs/ai/game_rival_watchlist.json --allow-network

The client requests only the fixed public Steam News API endpoint, via read-only HTTPS, bounded app IDs, fixed paths and query fields, limited response length/item counts, timeouts, no HTTP redirects and no environment proxies. Only article GIDs, timestamps, approved URL hosts and digests survive admission. Third-party full article text, videos, copyrighted expression and instructions embedded in the news are not passed to training.

The scheduled GitHub workflow executes a daily snapshot only after it lands on the default branch; it stores 14-day read-only evidence artifacts. It cannot write repository changes, decide that a competitor is an enemy, create a production model or silently ingest raw web prose. Operational problems and absent feeds are recorded as source errors, not low rival scores. GitHub may delay scheduled runs.

An operator can review and classify observed public mechanics and compare against precommitted original plans using an exact JSON document containing:
- schema: skeleton.game_builder.competitor_analysis_request.v1
- plan: a PlannedTitle payload with schema, original signature and DesignFacet records
- rival: a CompetitorTitle payload
- signals: a list of reviewed PublicSignal payloads
- benchmarks: optional list of independently reviewed QualityMeasurement payloads

Then:

    python -m skeleton.ai.game_builder.rival_watch_cli analyze --evidence reviewed_convergence.json --trusted-reviewer --ledger /trusted/competitor.db

The local CLI can accept a preexisting report using --previous-report to implement hysteresis. New reports use optimistic expected-head journal writes; stale head or corrupt historical events fail closed. The journal is SHA256 hash-chained and SQLite-transactional. External signatures and remote anchored heads remain needed to prevent a privileged operator from deleting or replacing an entire database or chain tail.

Actual game signoff similarly uses the exact typed schema skeleton.game_builder.competitor_delivery_request.v1, with plan, report and independently replayed DeliveryVerification. The command is:

    python -m skeleton.ai.game_builder.rival_watch_cli signoff --evidence delivery.json --trusted-reviewer

Neither analysis nor signoff causes an actual game to ship or an AI model to be promoted. The trusted-reviewer flag is not itself an identity credential; embedding production apps must authenticate and separate trusted reviewers and keep their receipts.

## 7. Adversarial safety and legal safeguards

- Enforce original identity signature equality and the actual original plan revision, not replacement with a rival look-alike.
- No rival assets, trademarked/expressive branding, scripts, cutscenes, protected storyline, character appearances, speech/audio or copyrighted content may be copied into original game deliverables.
- Rights clearance and similarity assessment remain with the canonical RightsLedger and existing game-builder release gates. No automated legal safety opinion is created.
- Do not use public video/blog/press evidence as training weights without separate permission to train. Research references and source quality weights are **not** neural weight updates.
- Prevent same-source evidence recycling, fabricated reviews, stale facts, mismatched benchmark protocols, unverifiable competitor leads and mathematical target impossibilities.
- Restrict public polling to an opt-in read-only official source domain. Harden against giant responses, wrong game app IDs, redirected endpoints, malformed JSON, oversized inputs, hostile copied headlines and time anomalies.
- Require independent benchmark and user-game proof for every reported completed order. "Tasks listed" and "work done" are separate facts.
- A competitor can be an ordinary market rival while its creators are respected, and inspiration can be drawn from unprotectable mechanics and facts only within legal/originality boundaries.

## 8. Next genuine implementation milestones

- Additional legally reviewable official platform announcements for console, PC, mobile and obscure/retro game eras, with checked platform terms.
- Authenticated independent reviewer identities, signed receipts, durable trust/revocation and externally anchored journal roots.
- Review queue that turns new daily monitored metadata into accurately sourced mechanic discoveries and long-term trends.
- A real governed dispatch bridge to Jeeves planning, Dragon/Wiki research, HOAG benchmarks, the forge's actual playable builder and Mirror adversarial evaluation, with resource budgets and an audited execution/quality loop.
- Hardware- and genre-adjusted comparative benchmarks, independent gameplay cohorts, publisher-dependence detection, uncertainty intervals and improvement ROI based on actual player experience.
- Stop-the-line rights/identity checks on every production artifact, not just typed completion reports, before shipping.

**Qualification target:** exact-head Ubuntu and Windows regression suites, verified source and identity boundaries, auditable revisions, actual gameplay benchmarking and independent release evidence before claiming any measured competitive superiority.
