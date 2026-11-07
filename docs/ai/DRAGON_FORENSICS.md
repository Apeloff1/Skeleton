# Dragon Atlas forensic review: thirteen additional inspection boundaries

Canonical owner: `skeleton/ai/webcrawler/dragon_campaign_stack/forensics`.
Optional entry points: `compose_atlas_forensics` and `verify_atlas_forensics`.
The forensic extension reads an immutable Dragon Atlas, canonical CrawlRun
snapshot and complete current source-policy projection. The existing
`compose_dragon_atlas` remains unchanged (26 stages); this adds an
thirteen-stage, independently sealed **review-only** chain.

## Trust and authority

- The authenticated caller provides the canonical snapshot and source policy.
  The extension starts by verifying the **full** existing Atlas trace, then
  reopens the canonical snapshot and validates every selected retrieval anchor.
- Current withdrawal identities must be present and identical in source policy
  and retrieval. Expired consent or changed source policy fails closed.
- The inspection is synchronous and offline. It neither fetches URLs nor
  writes Mongo or disk, starts workers, invokes language models or grants rights.
- Raw captured text is held only in private in-memory `Frame` instances
  during analysis. The returned `AtlasForensics` report is metadata only,
  with exact source IDs, SHA-256 anchors, rule codes and human-review tasks.
- A clean scan is not proof against prompt injection, unsafe source text,
  scientific error, copied work, false attribution or legal rights problems.
- No source or review task is automatically promoted as trusted knowledge;
  any downstream consumer must revalidate source authority again.

## Forensic stage contracts

| Boundary | Output | Failure behavior |
| --- | --- | --- |
| 1. Exact passage custody | Current source ID/hash, canonical host, objective IDs, selected passage offsets | Reject stale, withdrawn, re-anchored, duplicated or out-of-scope selected evidence |
| 2. Text security | Bidi and invisible Unicode, script mixing, instruction overrides, role spoofing, exfiltration and tool invocation signals | Explicit rule-coded human hold; never execute instructions |
| 3. Span geometry | Source window overlap, unique covered characters and disjoint regions | Review overlapping windows rather than double-counting evidence |
| 4. Reuse graph | Direct exact/near-copy edges, cross-host clusters and transitive unknown relationships | Treat lexical similarity as provenance hypothesis |
| 5. Objective resilience | Per-objective source removal, host removal and possible copy-family collapse | Report hypothetical evidence deficits, never certify independence |
| 6. Lexical padding | Unique-token ratios and repeated four-gram prevalence | Low-information review hold, not a quality or truth verdict |
| 7. Capture-age posture | Source capture time compared to operator maximum age | Old or unknown timestamps held; live origin freshness never inferred |
| 8. Sentence echoes | Cross-host normalized sentence hash collisions, without exporting sentences | Review potential cross-source echo without claiming proven copying |
| 9. Active content | Script, iframe, event handler, unsafe URL scheme and terminal escape signals | Never render or execute embedded payloads |
| 10. Privacy signals | Email, probable credentials and private key headers, rule codes only | Review without exporting matched values |
| 11. Host exposure | Concentration index and per-objective effective host count | Warn about source concentration, never infer independent authority |
| 12. Polarity leads | Same shared lexical core with opposite negation, sealed terms only | Investigate as possible disagreement, never claim factual contradiction |
| 13. Human review queue | Priority-sorted, snapshot/policy-bound rule-coded tasks | Fail rather than truncate over-capacity findings; no auto-resolution |

The thirteen receipts are hash-chained with explicit order, mandate, policy and
snapshot identity. SHA-256 offers internal tamper evidence, not a digital
signature, credential, independent source proof or user authorization.
`verify_atlas_forensics` rebuilds all eight stages from the provided current
canonical source, rejecting tampered review tasks, anchors or digest fields.

## Operator example

```python
from skeleton.ai.webcrawler.dragon_campaign_stack.forensics import (
    compose_atlas_forensics, verify_atlas_forensics,
)
report = compose_atlas_forensics(
    mandate, canonical_snapshot, atlas, now=now, authorized=True,
)
verify_atlas_forensics(
    mandate, canonical_snapshot, atlas, report,
    now=now, authorized=True,
)
# report.reviews.tasks is metadata for an authenticated human workflow.
# It is never a crawl, publication, model or consent authorization.
```

## Qualification and rollback

```sh
python -m compileall -q skeleton/ai/webcrawler/dragon_campaign_stack
python -m unittest discover -s tests -p 'test_ai_webcrawler_dragon_forensics.py' -v
```

Also run the existing Atlas and crawler source suites, backend auth/Mongo tests,
full merge/security gates and real-device tests before promotion. Source-only
tests are not proof of a working Windows laptop, native runtime, live worker,
correct rights or production launch. Rollback is to stop consuming this
additive extension or revert the feature commit; no database migration.
