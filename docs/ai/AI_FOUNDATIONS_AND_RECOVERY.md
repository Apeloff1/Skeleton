# AI workflow foundations and failure recovery

The chat, original-game studio and Dragon capture forms share bounded workflow
templates. These configure a new draft; they do not start a job, authorize edits,
grant source rights, enable automation or activate a model.

## Start with a bounded draft

Open **Workflow templates** in either chat composer, the studio goal form or a
new crawler capture. Inspect the settings and requirements, then apply a template.
Your content, selected model, source URLs, project and consent remain under your
control. Review the ordinary form before submitting it.

Chat offers a direct-answer allowance and a reviewed-answer allowance. Reviewed
answers still require available cooperative roles and a compatible model budget.
Studio starters stage finite action, model, job, output and time ceilings; the
separate run, edit and measured-review controls remain explicit. Crawler starters
stage request, document, byte and depth limits. They do not authorize timed
automation or fill in public seeds and source-use acknowledgements.

The application verifies catalog and template content digests, checks the current
authenticated account and reads the catalog again before Apply. Changing the
account, project, thread or model invalidates an outstanding Apply. A template
cannot silently replace an active workflow. Submission still goes through the
existing command owner's validation and current resource limits.

## Inspect local execution limits

Expand **Runtime optimization** in chat and select an installed local model.
Its execution contract reports activated context/output limits, supported
protocols, input-accounting basis and operator capacity. Exact tokenizer counts
and conservative byte estimates are distinguished. Reading this metadata does
not tokenize a prompt or invoke inference.

The local owner validates input, output and total-token limits before dispatch.
Native streams must agree with their terminal token IDs, event sequence and
replay identities before a result can be published or cached. These checks prove
consistency of the reported execution, not the correctness of generated content.

## Recover chat without duplicating work

An unconfirmed HTTP response is not proof that a turn failed or never ran. Inspect
the existing turn and its canonical operation identity before creating another
request. Ordinary network transport does not automatically replay a command.

The backend bounds the engine response while streaming it, applies the existing
absolute request allowance and rejects duplicate-key, non-finite or malformed
JSON. Terminal status, event and result identities must agree before the current
chat can be marked completed or failed. Malformed or foreign results are protocol
failures. Persisted turn/event rows must retain exact schema, scalar and record
identities, and lease renewal must remain future-valid on Mongo's clock.

## Understand learning and maintenance observations

Learner explanations describe a small operational predictor's local response to
normalized numeric features. They are available only for ready, current evidence.
They include scoped model/state/policy/sample fingerprints and never expose
prompts or answers. A signed sensitivity is not causal feature importance, game
quality or factual correctness. A retained reference sample is historical;
latest-source metadata is explicitly about the state rather than that sample.

Corrupt whole-state integrity cannot be repaired by trusting a checkpoint embedded
inside the same corrupt data. The learner quarantines it. Checkpoint replay
admission checks canonical execution and feedback metadata as well as retained
diagnostic hashes. Export a healthy checkpoint before an intentional reset or
replacement; importing it does not restore production-model authority.

Maintenance inspection lists actual local handlers, queue counts and observed
scheduling blockers. Ages and backoff use the last persisted host logical clock.
**Awaiting host admission** does not promise current idle capacity. Actual work
must pass host resource, foreground, policy, handler and physical-custody checks.
Drain callbacks run outside persistence locks; only an exact committed positive
proof permits a locked claim to recover custody. Expiry alone is insufficient.

Completion acknowledgements retire pending receipts only after a successful void
hook or an explicit bounded acknowledgement. A malformed response remains pending
for recovery and does not re-execute already committed optimizer work. Existing
failed-task retry and circuit-reset controls preserve their exact source and
failure bindings.

## Keep builds truthful under pressure

Galaxy's existing build owner retains task handles and physical-worker custody
while stopping work. A stale heartbeat or elapsed client clock does not establish
completion and cannot justify an overlapping replacement runner. Storage,
memory and deadline failures stop further production and preserve known partial
artifacts rather than manufacturing completed phases or accumulating an
unbounded in-memory fallback. Inspect the actual failure and restore capacity
before starting replacement work.

This pass was checked through source compilation and bounded static build checks.
No tests, inference, training, crawler or simulation workloads were executed.
Runtime reliability and enterprise qualification remain unverified.
