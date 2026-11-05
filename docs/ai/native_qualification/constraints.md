# constraints — actual local model qualification

**Fixtures:** `skeleton/ai/runtime/operational_ai/native_qualification/cases/v1/constraints/`

This is an independent set of 24 original, source-bound inference tasks.
Each one contains its prompt, fixed expected assertions, source rights marker,
severity and reproducible sampling inputs. This domain detects regressions
or capability gaps in the **real** local model; it does not emit a score
until the real native runtime has generated and durably committed results.

## Acceptance protocol

- Confirm a digest-pinned operator-supplied checkpoint and tokenizer.
- Run the cases through `OfflineAIService.turn`, never a fixture backend.
- Preserve session revision, model/tokenizer identities and output digests.
- Apply deterministic assertions to the generated text, not to a canned answer.
- Treat failed inference, empty text and incomplete outputs as failures.
- Keep raw private prompts/answers outside ordinary public result artifacts.
- Do not treat static unit tests as model-quality or release proof.

## Scope and threat model

Test domain: `constraints`. Twenty-four cases cover multiple inputs and
formatting constraints; source corpus is original and has no third-party
model rights claims. This suite is a **measurement tool**. It cannot prove
that unrelated tasks, real-world safety, security, device compatibility,
training rights or consumer installation are qualified.

A passing domain result must be backed by actual native receipts bound to
a complete, byte-verified corpus inventory. Neither code compilation nor
pre-existing fixture JSON is a passing score.
