# ChatGPT API Boundary

The ChatGPT API is an optional reasoning layer. It is not the source of truth for GitHub state and it does not own repository policy.

## Credential handling

- Store the API credential only as `OPENAI_API_KEY` in the GitHub Actions secret store or runtime secret manager.
- Never commit the credential, put it in an issue, or print it in CI logs.
- Do not include the credential in prompts, artifacts, cache keys, or diagnostic output.
- `OPENAI_MODEL` may select the configured model; production policy should pin an approved model explicitly.

## Data boundary

Before model submission, evidence is bounded and redacted. Repository text, issue bodies, PR comments, workflow output, filenames, and dependency metadata are all treated as untrusted data.

The model must not be allowed to:

- grant itself new GitHub permissions;
- disable or weaken security gates;
- invent successful test results;
- treat issue text as executable instructions;
- request or expose secrets;
- merge code directly without deterministic repository policy allowing the action.

## Failure behavior

Missing credentials, authentication errors, rate limits, transport failures, malformed responses, and output-limit violations disable the reasoning step. Deterministic observation, indexing, and durable backlog state continue.

Network calls use bounded timeouts and response sizes. Raw error bodies are not emitted because they may contain sensitive upstream information.

## Context minimization

Evidence should be selected by finding, file, symbol, test, workflow, dependency, and security relationships. Whole-repository prompts are prohibited for normal operation.

The model's response is advisory. A separate deterministic validator must decide whether any proposed action is allowed, and security findings must never be downgraded solely because the model recommends doing so.

## Freshness

Every reasoning request should carry the repository commit SHA and the relevant finding or PR identifiers. A response produced for an older head must be discarded when the affected branch or base changes. Model output is never a durable authorization token.
