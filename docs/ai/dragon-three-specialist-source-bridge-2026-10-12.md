# Dragon three-specialist source bridge — 2026-10-12

## Purpose
This implementation connects the canonical technical source atlas and reviewed-knowledge library to the Dragon's three signed idle-only hatchlings. It adds genuine code for task-specific discovery and source-version admission, not a new network crawler or evidence authority.

## Article specialist
Candidates come from the owner-scoped curated technical atlas, matched to signed Dragon focus/adjacent topics. Each selected article retains its canonical SHA-256 source ID, stage-zero policy identity, observed editorial timestamp, host diversity cap and rights-denying defaults. The editorial timestamp never asserts that the linked page was actually fetched.

## Video specialist
The lane accepts only typed discovery hints that match a registered canonical source whose media type is video_candidate. Unregistered, blocked, foreign-owner, changed-source and mislabelled sources cannot enter the plan. A video URL is not a downloaded video or transcript, and no video ingestion or AI training occurs here.

## Source-update specialist
The update lane requires an existing current, active, design-reference reviewed document with at least two intact revisions and a real changed source-text hash. The revision hint must equal the latest reviewed text digest, and researched tags must intersect the latest reviewed mechanic evidence. A caller-supplied publication timestamp is explicitly an unverified hint, not an attested publisher timestamp. Final independent review remains mandatory before recording any learning.

## Idle-only resource and consent gates
Before it examines research metadata, the bridge verifies a signed owner-bound nest and calls the existing resource-aware idle planner with an empty lead batch. Work requires the adult Dragon with all three eggs, five minutes of actual idle time, safe and current device telemetry, independent lane-consent switches and overall owner consent. Foreground activity, thermal pressure, battery restrictions and missing permission produce zero proposals.

## Synergy and bookkeeping
An update candidate already linked to a newly reviewed source suppresses a redundant concurrent article candidate. Cross-lane source references and duplicate video hints cannot silently inflate work. The final fair scheduler limits work across all three children. Existing signed nest records, reviewed document receipts and source policy job tables remain unmodified during planning. All actual XP improvements still require the separate reviewed-knowledge bridge. Ledger timestamps record observations and authoring, not inferred remote publication dates.

## Example trusted application integration
```python
feed = DragonNestSourceFeed(almanacs, atlas, nest_store)
preview = feed.preview(
    owner, sample=current_hardware_sample,
    at=utc_now, idle_since=last_user_activity_utc,
    now_seconds=sample_clock, authorized=True, consented=True,
    article_consent=True, video_consent=video_permission,
    updates_consent=update_permission,
    video_hints=bounded_registered_video_hints,
    update_hints=bounded_reviewed_revision_hints,
)
# preview.plan.assignments are research intents, NEVER I/O grants.
```

Workers must separately reacquire authenticated global resource grants, apply canonical DNS/redirect/robots/terms checks, inspect current rights and privacy consent, acquire evidence, and obtain independent Wiki/HOAG approval. No autonomous daemon, network fetch, memory promotion, model training or OS background task is started by this bridge.

## Validated scope and remaining work
Eight new integration tests cover articles, video, real changed source revisions, identical/replayed updates, cross-owner and media rejection, blocked policy jobs, idle and consent gating, source corruption, duplicate signals and bounded workloads. The Dragon AI Verification workflow now includes the new test module.

Run: python -m pytest -q --noconftest tests/test_dragon_technical_source_atlas.py tests/test_dragon_nest_source_feed.py

Next steps: link real application foreground/idle telemetry, resource-admitted workers, source publication evidence and independent approval into the companion. The wider accepted raw-link ledger currently contains 19,228/44,050 leads (43.65%), distinct from verified or approved content. The 55 curated source leads must not be automatically added to that total because they may overlap.
