# Punctuation — original independent SFT challenge

**Evaluation domain:** `punctuation`  
**Trust level:** normal functional evaluation  
**Source count:** 24 fixed original tasks.

## What this domain actually measures

remove only commas and preserve final punctuation. The source cases are concrete prompt, arguments and expected-answer
records, each with a stable identity, independent deterministic source oracle,
rights declaration, intended evaluation scope and cryptographic digest.
This is not a model training dataset.

All 24 prompts are source-authored and vary their task identity and inputs.
The oracle independently reconstructs the prompt and exact answer from the
scenario definition, rather than accepting whichever answer the JSON contains.
Tampering with an answer, argument, prompt, severity or provenance must cause
case admission to fail before native inference.

## Actual model evaluation

When an operator provides a trusted, hash-verified native checkpoint, the
`challenge_executor` submits these original prompts through exactly the
same `NativeChatEngine` framing used for interactive chat. Responses come
from the real native transformer inference path, not a canned function.
The scorer compares actual response text to the independent fixed answer.

The result is a per-case correct/incorrect bit, measured token counts and
latency, model and tokenizer identities, replay receipt SHA-256, and hashes
of expected and observed text. No raw private transcripts are included in
public receipts.

These functional cases contribute to domain-balanced quality but do not substitute for the separately measured critical safety cases.

Neither a passing source fixture test nor positive model accuracy authorizes
production routing. The challenge is excluded from all SGD, vocabulary fitting
and validation-based checkpoint selection. Release remains a distinct,
fail-closed operator and exact-Git-head qualification decision.
