# Dragon exact-head CI unblockers — observed errors and minimal repairs
Authored 2026-10-12 UTC | PR #3605 | Feature branch feat/dragon-wisdom-review-20261010

## Observed check run on commit 63c4d7d

GitHub Actions run 38292773290 finally executed the real Dragon Python, Dragon Source Safety and Dragon Frontend jobs. All three reached their first substantive test/compile stage. Their original conclusions were failure, and those failures must not be presented as successful validations.

### 1. Dragon Python and Source Safety: curated atlas import fails

Both suites failed during pytest collection, before tests could execute. Stack trace ended in dragon_technical_source_atlas._curate with ValueError: invalid curated atlas seed. A deterministic audit of all 248 tuple rows found exactly one entry violating the slug validator: 8bitworkshop. The entry has a valid HTTPS public documentation link and otherwise valid terms/family, but the slug regex mistakenly restricted its first character to a letter.

Fix: allow a leading lowercase ASCII digit in the curated source slug validator while retaining the 2–40-character bound, lowercase ASCII/hyphen rules, uniqueness, canonical URL checks, and explicit non-authoritative metadata status. Preserve the original 8bitworkshop slug, avoiding unnecessary identity migration. New regression tests assert exact source URL, family, candidate-only rights and 248-row preservation.

### 2. Dragon Python: pytest parametrization cannot collect scheduler tests

File tests/test_ai_webcrawler_dragon_nest_research_scheduler.py marks test_no_video_article_mislabel with @pytest.mark.parametrize('kwargs', ...) but its function signature omitted kwargs. This is a pytest collection error unrelated to the scheduler runtime.

Fix: add the kwargs parameter; do not skip the two malformed video/article source tests.

### 3. Dragon Frontend: React Native progress bars fail typecheck

Both TypeScript errors TS2769 occurred in features/Jeeves/companion/DragonNestProgression.tsx at two style width expressions constructing a generic string with '+' and '%'. ViewStyle.width requires a React Native DimensionValue, which accepts a typed percentage string.

Fix: use one strictly typed helper returning a template literal type for bounded percentage widths; update both the mother and child progress bars. The previously successful companion component, canonical wire, wisdom and native-delivery checks remain in place.

## Retest gates

Because the feature branch push trigger is now present, these corrections will request fresh exact-head Python/Source Safety/Frontend checks. A passing compile or pytest collection is only the first gate; any subsequent runtime failures must be traced and corrected rather than hidden by xfail, skipped tests, weakened permissions or excluded modules.

## Scope and record

These changes do not grant a research source license, crawl a website, promote model weights, or award game XP. The 8bitworkshop source remains a candidate only.

2026-10-12 UTC improvements:
(Restored importability of all 248 technical source candidates.)
(Restored two intended scheduler safety test cases.)
(Corrected typed mother and hatchling progress-bar widths.)
(Converted hidden draft-branch CI failures into exact identified integration repairs.)