# Native Supervised AI — real completion-only CPU training

This is an AI-only implementation of original-data, native supervised
fine-tuning and independent evaluation. It introduces no gameplay,
scene, quest, asset or game-installation logic.

## Why this layer exists

The earlier model can initialize, compute native attention and logits,
perform SGD, and serialize checkpoint weights. That does not mean its
responses have been trained for chat. Earlier training used a generic
Instruction/Response string, while inference used length-delimited
ChatTranscript messages. Earlier SGD also optimized prompt tokens,
wasting gradient steps on reproducing the user's question.

This layer uses the identical ChatTranscript.format_prompt implementation
for both training and serving. It builds teacher-forced target windows
only for expected assistant response tokens. The native CPU optimizer
performs real backpropagation on these windows using existing TinyTransformer
functions, records actual step counts, validates loss with real logits,
and selects changed candidate weights only after measured improvement.

## Fixed original source

There are 576 rights-scoped training examples: 432 train, 72 validation,
72 holdout. Every item has original provenance, fixed purpose, source
identity and independently reconstructed expected answer. The vocab
comes only from train examples, and neither validation nor holdout data
receives gradient supervision.

Another 768 original cases over 32 challenge domains are used only for
model evaluation. These include arithmetic, parsing, structured text,
list operations, case transformations and strict operational permission
decisions. Each case carries fixed arguments, a regenerated expected
answer and a source SHA. There are 192 critical operational cases.

## Source versus model evidence

Reading 768 source cases is not the same as executing 768 model requests.
Only actual native generation receipts can prove which cases the model
answered correctly. The evaluator retains model/tokenizer identities,
per-case response hashes, replay digests, actual output token counts and
timings. Partial batches are never presented as a complete benchmark.

The local reference transformer is small and randomly initialized.
Positive training-loss improvement is not proof of broad language ability,
and its current lowercase word-level tokenizer cannot faithfully emit
many JSON, CSV, punctuation and case-sensitive outputs. The architecture
limitations are measured and surfaced, not removed from grading.

## Trust boundaries

No pretrained or unlicensed weights are committed. Candidate weights
are stored in private immutable, hash-addressed POSIX directories.
Any uncertain training or publication event remains held. The original
model never receives direct SFT gradients.

Training, evaluation, rollback and release use independent identities.
There is no automatic production model activation or GitHub merge.
Exact final-head CI, actual native model qualification and device tests
remain mandatory evidence for any release.
