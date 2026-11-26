# Original quest structural editing — Studio A

This source-complete operator flow extends original prompt quest compilation with
**atomic typed structural revisions**, rather than replacing a working compiler
with a catalog of inert content. It edits authored stage and ending graphs, then
recompiles the entire graph through the real sandbox quest engine.

The operator first creates a typed, origin-attested prompt quest compilation
and publishes it to a private directory. A bounded batch of up to 32 explicit
`{"op":"...","id":"...","value":...}` edits can add, replace, or remove a
stage/ending, reorder the stage sequence, or replace the prompt. Each operation
is schema-checked; graph validity is checked on the **whole candidate** after
all edits. Invalid dependencies, impossible ending requirements, stale CAS
leases, duplicate identities and unauthorized requests fail closed. The
baseline compilation remains unchanged.

CLI:

`python -m scripts.studio_quest_structural_edit_cli --baseline-dir OLD
--expected-baseline DIGEST --edits-json '[...]' --publish-candidate NEW`

`NEW` must already exist and be private. Publication uses the existing
exclusive no-overwrite fsynced prompt-quest receipt writer. `--html` renders
read-only CSP-restricted HTML without writing files. Reopening the candidate
uses the existing prompt quest CLI and canonical receipt replay.

Jeeves exposes `studio_quest_structural_edit` through the static router and
requires both operator authorization and **explicit authoring opt-in**. No
model-controlled permission fields are accepted. The tool itself is read-only:
it returns a typed candidate and a source-verified revision proof, not a claim
that it wrote a file.

For regression review, pass the baseline and candidate compilations to
`studio_quest_regression_matrix`; then use the existing prompt quest playtest
for an actual sandbox ending witness. None of these operations grants rights,
native engine validation or release certification. Deterministic fixtures
exercise atomic edit batches, graph rejection, CAS, persistence, CLI, Jeeves
permission gates and actual quest replay.
