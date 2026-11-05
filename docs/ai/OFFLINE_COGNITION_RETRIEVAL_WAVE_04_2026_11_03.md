# Offline cognition wave 4 of 8: retrieval and exact-byte evidence

Eight additional source-controlled families implement bounded lexical and dense
retrieval, hybrid ranking, passage reranking, source attribution, byte-verified
citation, Unicode-safe chunk partitioning and duplicate filtering.

This is inside the existing operational AI owner and uses the established
source receipt, resource, model SHA and identity contracts. It does not add a
new provider, service, database, workflow trigger or model-runtime owner.

Dense vectors MUST come from a separately attested, operator-approved model
with an exact digest; the pipeline never fabricates embeddings. The only model
generation owner remains the existing real GGUF supervisor. BM25 statistics
are computed within the exact tenant and subject, not from other owners.

Cryptographic byte verification is not a semantic proof of an answer.
Corpus fixtures, casebooks and fake-worker contracts do not qualify real GGUF
weights, model rights, native tokenization or Windows laptop installation.

Local source regression command after complete branch:
    python -m unittest discover -s skeleton/testing -p 'test_offline_cognition_*.py' -q
    python -m unittest skeleton.testing.test_offline_cognition_evidence_pipeline -v

Operator failure taxonomy:
- Unapproved or modified source: reject without indexing.
- Cross-tenant or cross-subject batch: reject whole batch.
- Dense model SHA or vector dimension mismatch: reject; no fallback.
- Forged span, quotation, source ID or content digest: reject.
- Resource ceiling or no forward progress: reject.
- Damaged projection: reconstruct from external authorized original receipts.
- Model or device missing: hold native execution, do not synthesize replies.
- Any failed, skipped or missing exact-head check: hold promotion and release.

L00-L13: canonical AI owner preserved; authority checked before processing;
finite source, token, vector and span limits; cross-scope refusal; projection
rebuild instead of invented state; source-controlled adversarial tests;
observable digest receipts with no stored prompt or secret; no new deployment
surface; release and comparator-backed superiority remain unqualified.
