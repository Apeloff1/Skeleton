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

Maintenance startup remains non-admitting until its owner has synchronized the
actual foreground count. Controller initialization and foreground transitions
share the existing activity lock, and maintenance opens the literal foreground
execution database path. Callback results are detached and bounded before
serialization. Failed tasks with unverified completed chunks remain available
as retry targets instead of disappearing during history compaction.

## Reconnect and shut down without losing ownership

Foreground reconnect and **Check status** inspect the existing chat operation.
They do not resubmit a request. **Resume** is an explicit action with the retained
request identity. Stop intent remains attached to that identity, including an
ambiguous first submission. Failed conversation loading can be retried, and local
drafts and attachments remain associated with their actual thread and verified
account. The conversation file view contains actual authorized attachments.

If a saved key is unknown after process loss and the original request settings
are unavailable, the UI retains the unresolved key. A 404 does not prove that a
late request cannot arrive. Inspect it again or explicitly start another
conversation; the app does not invent successful cancellation or reconstruct
unknown execution settings. Mongo preparation recovery uses primary reads,
database-clock ownership and exact event/lease comparisons so a stale reader
cannot delete a newer writer's journal entry.

Local model identity checks, token preparation and generation share fair physical
worker admission. They run off the async event loop and retain the original
input/output ceilings through cache hits and shared requests. A closed engine
cannot be resumed as if it were an ordinary reversible maintenance drain.

Engine shutdown closes each actual serving engine once, including a separately
configured local verifier. Native work and lifecycle leases must drain before
database custody and Mongo finalization dependencies are released. Failed
cleanup retains its exact handles for retry and blocks replacement startup.

## Keep builds truthful under pressure

Galaxy's existing build owner retains task handles and physical-worker custody
while stopping work. A stale heartbeat or elapsed client clock does not establish
completion and cannot justify an overlapping replacement runner. Storage,
memory and deadline failures stop further production and preserve known partial
artifacts rather than manufacturing completed phases or accumulating an
unbounded in-memory fallback. Inspect the actual failure and restore capacity
before starting replacement work.

A positive explicit `target_files` is a ceiling on unique generated paths for
the main build. It overrides scale text and size hints, disables delivery
padding, and applies to nested and fallback generation. When it interrupts an
unfinished phase, the build reports `artifact_file_budget_exhausted` and retains
the accepted partial files durably, including through manual advance. A tiny
installation probe therefore proves bounded generation and retention; it does
not prove a completed or playable game. Later artifact jobs retain their own
bounds.

Galaxy's shared HTTP dispatch uses the existing account role policy. Build and
artifact reads require sign-in; mutations require an editor and vault
maintenance requires an administrator. New builds retain the verified account
and tenant identity, which also scopes source/status reads, private lists and
derived build jobs across extracted routers. Old unowned installation records
remain available only to the administrator in the default installation tenant;
they are not assigned to whichever consumer signs in next. Global storage and
service controls also require that installation administrator. HTTP source
pruning requires one explicit authorized build; an empty request cannot erase
every build's source history.

Expansion, ZIP and APK preparation share that same physical slot in the backend
process. This is not a distributed multi-host lease. Expansions
save small chunks; packaging streams vault files in workers instead of loading
the whole game on the API event loop. A packaging job has its own result and
cannot retroactively mark the original game phases complete. Inspect the current
artifact operation and its actual stop/drain state before submitting another.

ZIP publication uses a unique staged file and an atomic final replacement.
Vault reads and corruption repair serialize with append, compressed manifests
cannot shadow a newer manifest, and only complete shards enter publication.
File counts describe unique current paths; replacing a path is not another file.
Explicit vault pruning cannot run while another operation owns the artifact slot.

Cloud APK commands remain explicit and subject to the existing execution switch.
The owner records submission intent before requesting an EAS build and reports
remote submission only after an acknowledged build ID. An uncertain response
retains its unresolved state and blocks automatic resubmission. Inspect the
remote service with the installation operator before attempting recovery.

## Interpret first-install readiness

The setup page observes public backend, engine and Mongo health separately from
authenticated storage admission, AI chat and Dragon prerequisites. It clears
account-specific observations on an account change. A viewer can inspect sources
but needs the existing owner to assign an editor/admin role before running web
captures. Capturing pages does not require a chat model.

Health responses must match the actual service protocol; HTML or a redirected
login page is not a healthy AI engine. Public status readers share one retained
bounded observation, including off-loop control-plane I/O, and a one-second
completed cache preserves its original observation timestamp. A deadline reports
unobserved state while that same work retains custody. Model configuration and
service liveness remain separate from actual model availability.

Frontend JSON requests bound streaming response buffering where the platform
exposes a readable stream. Native adapters exposing only `text()` retain their
platform buffering, followed by size rejection before parsing; absolute caller
deadlines and cancellation still apply. Credential-bearing requests do not use
the account-blind public session cache.

This pass was checked through source compilation and bounded static build checks.
No tests, inference, training, crawler or simulation workloads were executed.
Runtime reliability and enterprise qualification remain unverified.
