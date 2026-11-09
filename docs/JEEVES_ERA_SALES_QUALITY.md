# Jeeves era / console / genre / period sales + asset quality

## Policy: qualified reference cohorts, original creations

Use **two independent axes** of commercially successful and critically well
reviewed game references for the same era, console, genre and 1-10 year
release period. Reach (sales) and reception (reviews) are not identical to
artistic quality or profitability. Reference research NEVER grants rights to
copy assets, game code, story, music, recognizable worlds or trademarks.

Never invent sales figures or scores. The local JSON file is operator-supplied
evidence, with explicit source citations, not automatically trusted facts.

Source priorities: issuer financial statements / audited title sales, then
independent market research; independent professional critic aggregates or
documented periodical review archives for the review-quality axis.

Public methodological anchors:
- Publisher unit disclosures: Nintendo IR title level worldwide sales
  https://www.nintendo.co.jp/ir/en/finance/software/switch.html
  Official disclosures include downloads and hardware bundles, so basis
  and coverage matter.
- Review count and historical ratings: Metacritic describes at least
  seven professional reviews for its game-of-the-year rankings.
  https://www.metacritic.com/pictures/every-metacritic-game-of-the-year-winner/

### Data file

Place design/market_benchmarks.json in the original game workspace.

    {
      "schema":"skeleton.game.market_quality.v1",
      "cohorts":[{
        "era":"extraction_now", "console":"PC", "genre":"RPG",
        "period":"2015-2019", "records":[]
      }]
    }

Each populated record has exactly nine keys: id, release_year,
sales_units, sales_basis, sales_scope, critic_score, critic_reviews,
sales_source, rating_source. Each source contains exactly url, issuer, kind,
published. URLs must use HTTPS, be distinct between sales and ratings, and
include an issuer and actual YYYY-MM-DD publication date.

Sales measurement basis: sell_through, reported_units or shipments.
Scope: global_lifetime or regional_lifetime. Bases and scopes must be
identical across all games in the cohort. Critic score is 0-100 and review
count is an observed positive integer. Title release years must fall in the
selected interval. Title identifiers must not duplicate within a cohort.

Sales source kinds: publisher_filing, audited_sales, industry_research.
Quality source kinds: critic_aggregate, review_archive, independent_review.

A cohort requires 5 or more distinct titles, at least 3 different sales
figures and rating figures, and at least seven critic reviews for EVERY title.
To qualify as top-tier, a title must simultaneously be in the top quartile
of both unit sales AND quality score, have score >=85/100 and >=7 critic
reviews. Equal measured values share rank. Zero qualified titles means
FAIL CLOSED, not dilution or alternate-platform substitution.

    python -m skeleton dev game jeeves benchmark --project . --console PC --genre RPG --period 2015-2019
    python -m skeleton dev game jeeves benchmark-matrix --project .

The matrix lists all declared cohorts and their gaps. It does not pretend
the dataset covers every console or the complete history of gaming.

### Connect model authoring to a qualified cohort

    python -m skeleton dev game jeeves propose --project . --kind asset --brief "Original readable character silhouette" --console PC --genre RPG --period 2015-2019

For asset, animation, cutscene and music text proposals, a qualifying
cohort is REQUIRED. Other design kinds can optionally opt in to market
evidence. Model context includes only aggregate sales/critic ranges,
target cohort and quality/originality instructions, NEVER named commercial
titles or third-party copyrighted media. A proposal binds the exact source
file hash. Any market-profile drift before review or acceptance invalidates it.

### Asset rendering static preflight

    python -m skeleton dev game jeeves asset-gate --project . --console PC --genre RPG --period 2015-2019 --evidence design/asset_qa.json

Evidence JSON must contain: schema = skeleton.game.asset_quality_receipt.v1,
kind (asset, animation, cutscene, music), asset_path under assets/, sha256
of the actual file, originality = original, qa_scores with every category
dimension >=90/100, reviewers (2-8 DISTINCT named reviewers), performance
with measured_ms, budget_ms and platform matching selected console.

Dimensions per kind:
- asset: silhouette, readability, era_fidelity, material_detail,
  art_direction, accessibility, originality.
- animation: silhouette, timing, motion_clarity, transitions,
  era_fidelity, accessibility, originality.
- cutscene: composition, camera_continuity, timing, lighting,
  story_clarity, era_fidelity, originality.
- music: motif, mix_clarity, dynamic_range, loop_quality,
  era_fidelity, originality, accessibility.

Only PNG static/animation image, GIF animation, MP4 cutscene and WAV audio
containers are presently recognized. PNG is checked chunk by chunk,
including bounds and CRCs; other containers have only basic signature
checks. Invalid, symlinked, oversized or changed assets fail closed.

CRITICAL: operator-entered QA scores and runtime timings are NOT actual
independent quality verification. The current asset-gate validates evidence
shape, file identity and selected container integrity; it does not render
every console, independently observe a QA panel, assess aesthetics, decode
all audio/video, or approve game releases. The output deliberately leaves
production_qualified=false and peak_quality_proven=false.

### Ownership, limits, risks, and rollback

- Benchmark file cap 2 MiB; max 80 cohorts and 512 records per cohort.
  Render assessment cap 64 KiB receipt, 128 MiB asset, bounded reads.
- Benchmarking is read-only and entirely local; no scraping or inference.
  Only explicitly invoked design proposals call the canonical governed
  AI provider; no parallel provider or training authority is added.
- No source data is promoted to protected memory or model weights.
  No overwrite of existing authorship; old proposals become stale when
  matching benchmark context changes. No implicit background renderer.
- Gap: full historical sales ingestion, independent URL/source corroboration,
  review-methodology calibration, actual era-specific performance measurement,
  art review/renderer qualification, legal assessment and live E2E CI.

Tests: python -m pytest skeleton/testing/test_jeeves_game_quality.py
skeleton/testing/test_jeeves_game_authoring.py -q
