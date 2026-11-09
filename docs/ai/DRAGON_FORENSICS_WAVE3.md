# Dragon forensic source quality and custody — wave three

Four source-only stages extend the thirteen-stage forensic source trace to
seventeen staged receipts. This work is additive to the canonical twenty-six
stage Dragon Atlas; it is not a new crawler transport, storage authority or
automatic knowledge-approval path.

- **Canonical provenance posture** compares selected source identity, provenance
  receipt, content hash, raw-body availability, extraction truncation and
  consent binding. Identity violations reject immediately; extraction
  limitations produce human-review holds.
- **Operator objective grounding** computes whether the source-only selected
  passages actually satisfy required and blocked operator terms. Lexical
  matches are only candidates, not verified factual answers.
- **Selected reference concentration** measures exact selected passage
  reuse across objectives and sources, ensuring citation multiplicity cannot
  be mistaken for independent confirmation.
- **Consent expiry horizon** projects how close the mandate is to expiry;
  it never invents per-source policy expiry timestamps, cannot extend consent
  and does not authorize future captures or publication.

All four modules consume only the verified source-bound `FrameSet`, mandate
and immutable canonical snapshot. The forensic assembly chains their receipt
digests ahead of the review queue. The queue receives high or medium risk-coded
holds without source-body text.

Invocation: `compose_atlas_forensics(mandate, snapshot, atlas,
now=now, authorized=True)`, then `verify_atlas_forensics(...)`. A downstream
consumer must still re-check the Mongo source-use policy at actual use time.

Source-only qualification:
`python -m unittest discover -s tests -p 'test_ai_webcrawler_dragon_forensics.py' -v`
and `test_ai_webcrawler_dragon_deep_forensics.py`.
Real backend authorization, Mongo custody, native device tests, license
review and final-head security gates remain independent blockers.
