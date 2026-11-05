# Native lexical representation limitations

The CPU TinyTransformer uses the existing word-level tokenizer unless
an independently qualified tokenizer is attached. The default path
lowercases text, drops punctuation, and reconstructs output by joining
tokens with spaces. This is an architectural limitation, not a missing
prompt hint.

The default model cannot reliably emit exact JSON objects, comma-separated
CSV rows, uppercase identifiers, case-sensitive names, original punctuation
or many symbols. A tokenizer that cannot represent an output cannot learn
to generate it exactly, regardless of training duration.

Representability diagnostics perform an actual encode/decode round trip
for each challenge's expected output using the model's tokenizer.
Lexical diagnostics separately report unknown prompt and answer tokens
for all 768 evaluation cases and 32 domains. Neither diagnostic modifies
the vocabulary, substitutes model output, or claims quality.

No unrepresentable case is exempted from the evaluation denominator.
No hidden deterministic postprocessor transforms a wrong model answer
into a purportedly correct one. The discrepancy is surfaced for
engineering review.

A future reversible tokenizer must preserve full original case and
punctuation and encode arbitrary supported Unicode. Its snapshot and
digest must be pinned into model and checkpoint identity. All train,
validation, challenge and inference paths must switch to the same
codec, with explicit tests for round-trip parity and no data leakage.
Old trained weights must not be reused with a silently changed
tokenizer.

The current code intentionally remains honest about these limits.
A real native gradient and real model generation are not equivalent
to a broadly competent language model.
