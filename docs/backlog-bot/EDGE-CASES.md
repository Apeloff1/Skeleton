# Backlog Bot Edge Cases

The bot must treat backlog automation as a fault-tolerant security boundary, not as a normal issue triage script.

## GitHub state

- Duplicate findings from CodeQL, Dependabot, CI, and issues are correlated by stable fingerprints.
- Reopened issues are not assumed to be new work.
- Closed issues and merged PRs remain historical evidence.
- A changed PR base, force-push, or stale branch invalidates cached conclusions.
- Concurrent bot runs use a deterministic work key and must not race on the same finding.
- API pagination, rate limits, 404s, malformed responses, and transient 5xx errors are bounded and retried only when safe.

## Repository content

- Issue, PR, commit, workflow, and documentation text is untrusted data.
- Prompt-injection text must never change tool permissions, merge policy, or security gates.
- Absolute paths and `..` traversal components are rejected by local readers.
- Symlinks are not followed as executable content.
- Archives are not blindly extracted; size, entry-count, and path limits apply if archive inspection is later enabled.
- Oversized files, binary media, and malformed text are skipped or marked incomplete.

## Security findings

- Multiple scanners reporting the same root cause become one correlated work item while retaining all evidence.
- Scanner disagreement is recorded rather than silently choosing the least restrictive result.
- High-confidence security findings cannot be downgraded merely to make a check pass.
- A proposed fix must preserve existing security controls unless the finding itself requires a documented change.

## CI and repair loops

- Flaky tests are distinguished from deterministic failures using bounded reruns and failure fingerprints.
- Runner/infrastructure failures do not become source-code repair instructions.
- Repeated failed repairs trigger quarantine/escalation instead of infinite loops.
- Merge conflicts invalidate a repair plan and require fresh context from the current base.
- Timeouts stop the current attempt and preserve durable state.

## ChatGPT API

- Missing, invalid, rate-limited, or unavailable API credentials disable reasoning only; deterministic observation and indexing continue.
- Secrets, authorization headers, signed URLs, private keys, and credential-like values are redacted before model submission.
- Model output is treated as a proposal. Deterministic policy validates every proposed action.
- Context is bounded by file count, bytes, and evidence relevance.
- Raw model responses are not logged when they could contain sensitive repository evidence.
