# Dragon Atlas forensic expansion — wave five

The sealed forensic source review chain now consists of twenty-six ordered
metadata-only stages, in addition to the existing twenty-six source-bound
Dragon Atlas stages. The fifth wave introduces six new source-quality and
operational assurance projections.

1. **Extraction fidelity**: bound text-size, markup residue, encoded HTML
   entities, repeated characters, navigation boilerplate and whitespace
   artifacts. Findings are rule codes and source IDs, not reproduced text.
2. **Operator query-to-evidence support**: reconcile exact selected anchor
   identities, ranking query indices, reciprocal or BM25 rank sources, and
   operator objective IDs. Reject forged or out-of-scope rank references.
3. **Origin/redirect hygiene**: inspect captured canonical and fetched URLs,
   count tracking and potentially sensitive query-parameter *names*, flag
   redirect and scheme changes. Never return raw paths, tokens or full URLs.
4. **Selection fairness**: weighted per-objective source and host concentration,
   effective selected sources and normalized source diversity. Not proof of
   true independence or factual accuracy.
5. **Conservative risk-source ablation**: independently measure how many
   selected passages remain after hypothetically withholding sources flagged
   for prompt injection, privacy, active content, extraction or origin issues.
   No actual source is revoked and no automatic recrawl occurs.
6. **Unicode-script lexical coverage**: highlight potential operator-term
   blind spots when non-Latin selected passages receive ASCII-only lexical
   query terms. Script detection is heuristic and is not language ID.

Every stage remains source-bound and policy-bound through the existing
verified Atlas and exact-span source frame. Outputs are deterministic bounded
receipts with no source text, network, model use, external side effects or
autonomous publication. Review holds are appended before the final
`review_only_forensic_queue` stage. The client pins all stage names in order
and rejects missing or reordered entries.

## Validation

```sh
python -m compileall -q skeleton/ai/webcrawler/dragon_campaign_stack
python -m unittest discover -s tests -p 'test_ai_webcrawler_dragon_forensics.py' -v
python -m unittest discover -s tests -p 'test_ai_webcrawler_dragon_wave5.py' -v
python -m unittest discover -s backend/tests -p 'test_dragon_atlas_bridge.py' -v
```

Source-only tests do not certify actual HTTPS requests, DNS pinning, native
runtime installation, Mongo permissions or production release. All required
merge and security gates remain active, and skipped jobs are not passes.
