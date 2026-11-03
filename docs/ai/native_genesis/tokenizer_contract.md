# Native tokenizer construction and leakage rules

The tokenizer vocabulary must be formed from the 432 TRAIN lines only,
using the `skeleton.cortex.port.tokens` grammar already implemented by the
native transformer. This source fitting rule prevents implicit sampling
from validation, holdout, benchmark or model-generated answers.

Document frequency is computed per training line, not raw token frequency.
The default minimum frequency of one preserves every lexical form observed
during training, giving a measured train token-coverage ceiling of 100%.
Higher frequency thresholds are operator choices and may reduce coverage;
they must pass the same admission gate.

Unknown words in validation and holdout remain unknown; never expand the
vocabulary after evaluation begins merely to improve reported metrics.
No silent truncation is allowed when the maximum vocabulary is reached.
The operator must select a larger declared ceiling and rerun the full
source/model qualification path.

The native `TinyTransformer` adds its own unknown-token row. Compare
the actual model token inventory to the source-derived vocabulary before
checkpoint materialization. The model runtime's independent tokenizer digest
must match after checkpoint restoration.

Token counts and coverage are measured facts; they are not language-model
accuracy or safety measurements. Production usability needs real held-out
output evidence and independent review.
