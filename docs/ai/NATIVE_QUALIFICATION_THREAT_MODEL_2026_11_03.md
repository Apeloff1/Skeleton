# Native qualification threat and trust model

**Trust roots:** operator-owned model file, independently recorded expected
checkpoint digest and license, principal binding, canonical case source
recorded in the Git commit, verified local tokenizer and native inference
engine, private SQLite and filesystem root.

**Untrusted inputs:** model-generated text, external evidence in grounding
prompts, prompt-injection strings, benchmark questions presented as data,
unreviewed license assertions, model success claims and user-controlled paths.

**Threats addressed:** benchmark grade substitution, canned model responses,
mismatched tokenizers, session replay, secret-bearing raw report fields,
case-dropping grade inflation, source-citation swaps, invalid JSON, report
tamper, duplicate run IDs, anonymous release claims and branch drift.

**Controls:** the real-service type gate, actor/model digest checks,
full source-case digest comparisons, strict JSON, bounded step and output
budgets, deterministic checks, SQLite session commit, content-addressed
reports, no-clobber file publication and optional keyed HMAC chain.

**Explicit limitations:** static assertions are not semantic truth judges;
exact format checks may reject reasonable alternative prose. The included
prompt-injection and privacy tasks are finite probes, not comprehensive safety
proofs. The local model may fail all probes. No model weights or installer are
included. Scores do not certify output safety, fairness, security, or rights.
Real checkpoint execution and independent CI must be observed separately.

**No implicit fallback:** inference errors count failed cases, not a switch to
a hosted provider or test fixture. The evaluator never directly executes
generated shell commands, network requests or filesystem writes.
