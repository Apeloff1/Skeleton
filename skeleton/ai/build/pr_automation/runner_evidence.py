"""Evidence collection and normalization for the PR automation runner.

The collector turns GitHub's mutable REST/GraphQL payloads into one immutable
`RunnerSnapshot`.  It fails closed on incomplete pagination, ambiguous provider
state, malformed identities, review-thread truncation, or an observed base head
that does not match the pull-request base SHA.

Unlike the legacy adapter this module preserves normalized evidence so reports
can explain exactly which check, review, file, and branch observation produced a
decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

from .core import CIState, PRSnapshot
from .runner_contracts import (
    CheckEvidence,
    CheckState,
    EvidenceCompleteness,
    FileEvidence,
    ReviewEvidence,
    RunnerPolicy,
    RunnerSnapshot,
    ci_state_from_checks,
    parse_time,
    unique_text,
    utcnow,
    valid_sha,
)
from .runner_transport import BudgetedGitHubTransport, RunnerTransportError


TERMINAL_FAILURES = frozenset(
    {
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
        "startup_failure",
        "stale",
    }
)
PENDING_STATES = frozenset(
    {"queued", "in_progress", "pending", "requested", "waiting"}
)
SENSITIVE_PREFIXES = (
    ".github/workflows/",
    ".github/actions/",
    ".github/ci/",
    "skeleton/pr_automation/",
    "security/",
)
SENSITIVE_FILES = frozenset(
    {
        "scripts/check_merge_readiness_contract.py",
        "scripts/check_automerge_contract.py",
        "scripts/quality-gates.sh",
        "tests/run_unit.py",
    }
)


class EvidenceError(RuntimeError):
    """Raised when a complete trusted snapshot cannot be produced."""


THREADS_QUERY = """
query(
  $owner:String!,
  $name:String!,
  $number:Int!,
  $cursor:String
) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(first:100, after:$cursor) {
        nodes {
          isResolved
          isOutdated
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
}
"""


def _int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _sha(value: object, *, field: str) -> str:
    text = str(value or "").casefold()
    if not valid_sha(text):
        raise EvidenceError(f"{field} must be a canonical 40-hex SHA")
    return text


def _state_from_check_run(run: Mapping[str, Any]) -> CheckState:
    status = str(run.get("status") or "").casefold()
    conclusion = str(run.get("conclusion") or "").casefold()
    if status != "completed":
        return CheckState.PENDING
    if conclusion == "success":
        return CheckState.PASSING
    if conclusion == "skipped":
        return CheckState.SKIPPED
    if conclusion == "cancelled":
        return CheckState.CANCELLED
    if conclusion in TERMINAL_FAILURES:
        return CheckState.FAILING
    return CheckState.UNKNOWN


def _state_from_status(status: Mapping[str, Any]) -> CheckState:
    state = str(status.get("state") or "").casefold()
    if state == "success":
        return CheckState.PASSING
    if state in {"failure", "error"}:
        return CheckState.FAILING
    if state in PENDING_STATES:
        return CheckState.PENDING
    return CheckState.UNKNOWN


def _check_provider(run: Mapping[str, Any]) -> str:
    app = run.get("app")
    if isinstance(app, Mapping):
        slug = str(app.get("slug") or "").strip()
        app_id = _optional_int(app.get("id"))
        if slug and app_id is not None:
            return f"{slug}:{app_id}"
        if slug:
            return slug
        if app_id is not None:
            return f"app:{app_id}"
    return "unknown-check-provider"


def _status_provider(status: Mapping[str, Any]) -> str:
    creator = status.get("creator")
    if isinstance(creator, Mapping):
        login = str(creator.get("login") or "").strip()
        creator_id = _optional_int(creator.get("id"))
        if login and creator_id is not None:
            return f"{login}:{creator_id}"
        if login:
            return login
    return "legacy-status"


def normalize_check_run(
    run: Mapping[str, Any],
    *,
    expected_head_sha: str,
) -> CheckEvidence | None:
    name = str(run.get("name") or "").strip()
    if not name:
        return None
    raw_sha = str(run.get("head_sha") or expected_head_sha).casefold()
    if not valid_sha(raw_sha):
        return None
    if raw_sha != expected_head_sha:
        return None
    source_id = _int(run.get("id"))
    return CheckEvidence(
        name=name,
        provider=_check_provider(run),
        state=_state_from_check_run(run),
        source="check_run",
        source_id=max(0, source_id),
        head_sha=raw_sha,
        started_at=(
            str(run.get("started_at"))
            if run.get("started_at") is not None
            else None
        ),
        completed_at=(
            str(run.get("completed_at"))
            if run.get("completed_at") is not None
            else None
        ),
        updated_at=(
            str(run.get("updated_at"))
            if run.get("updated_at") is not None
            else None
        ),
        details_url=(
            str(run.get("details_url"))
            if run.get("details_url") is not None
            else None
        ),
    )


def normalize_status(
    status: Mapping[str, Any],
    *,
    expected_head_sha: str,
) -> CheckEvidence | None:
    name = str(status.get("context") or "").strip()
    if not name or name == "PR Automation Gate":
        return None
    source_id = _int(status.get("id"))
    return CheckEvidence(
        name=name,
        provider=_status_provider(status),
        state=_state_from_status(status),
        source="commit_status",
        source_id=max(0, source_id),
        head_sha=expected_head_sha,
        started_at=(
            str(status.get("created_at"))
            if status.get("created_at") is not None
            else None
        ),
        completed_at=None,
        updated_at=(
            str(status.get("updated_at"))
            if status.get("updated_at") is not None
            else None
        ),
        details_url=(
            str(status.get("target_url"))
            if status.get("target_url") is not None
            else None
        ),
    )


def newest_provider_evidence(
    evidence: Iterable[CheckEvidence],
) -> tuple[CheckEvidence, ...]:
    """Select the newest record for every check-name/provider/source tuple."""
    latest: dict[tuple[str, str, str], CheckEvidence] = {}
    for item in evidence:
        key = (item.name, item.provider, item.source)
        prior = latest.get(key)
        if prior is None or item.recency() >= prior.recency():
            latest[key] = item
    return tuple(
        sorted(
            latest.values(),
            key=lambda item: (item.name, item.provider, item.source),
        )
    )


def reduce_context_state(
    evidence: Iterable[CheckEvidence],
    *,
    context: str,
) -> CheckState:
    """Reduce all current providers for one named context fail-closed.

    A duplicated context from two providers is only passing when every current
    provider is passing.  This prevents an old success from one integration from
    masking a newer failure or pending result from another integration that
    publishes the same context name.
    """
    states = [
        item.state
        for item in evidence
        if item.name == context
    ]
    if not states:
        return CheckState.MISSING
    unique = set(states)
    if CheckState.FAILING in unique or CheckState.CANCELLED in unique:
        return CheckState.FAILING
    if CheckState.PENDING in unique:
        return CheckState.PENDING
    if CheckState.UNKNOWN in unique:
        return CheckState.UNKNOWN
    if CheckState.SKIPPED in unique:
        return CheckState.UNKNOWN
    if unique == {CheckState.PASSING}:
        return CheckState.PASSING
    return CheckState.UNKNOWN


def required_check_states(
    evidence: Iterable[CheckEvidence],
    required: Sequence[str],
) -> tuple[tuple[str, CheckState], ...]:
    current = newest_provider_evidence(evidence)
    return tuple(
        (name, reduce_context_state(current, context=name))
        for name in required
    )


def aggregate_ci_state(
    evidence: Iterable[CheckEvidence],
    required: Sequence[str],
) -> CIState:
    if required:
        states = [state for _name, state in required_check_states(evidence, required)]
    else:
        states = [item.state for item in newest_provider_evidence(evidence)]
    return ci_state_from_checks(states)


def normalize_review(
    review: Mapping[str, Any],
) -> ReviewEvidence | None:
    user = review.get("user")
    login = (
        str(user.get("login") or "").strip().casefold()
        if isinstance(user, Mapping)
        else ""
    )
    if not login:
        return None
    raw_commit = review.get("commit_id")
    commit_id: str | None
    if raw_commit is None or str(raw_commit).strip() == "":
        commit_id = None
    else:
        commit_id = str(raw_commit).casefold()
        if not valid_sha(commit_id):
            return None
    return ReviewEvidence(
        login=login,
        state=str(review.get("state") or "").upper().strip(),
        review_id=max(0, _int(review.get("id"))),
        commit_id=commit_id,
        submitted_at=(
            str(review.get("submitted_at"))
            if review.get("submitted_at") is not None
            else None
        ),
    )


def _review_rank(review: ReviewEvidence) -> tuple[datetime, int]:
    when = parse_time(review.submitted_at)
    if when is None:
        when = datetime.min.replace(tzinfo=timezone.utc)
    return when, review.review_id


def latest_decisive_reviews(
    reviews: Iterable[ReviewEvidence],
) -> tuple[ReviewEvidence, ...]:
    latest: dict[str, ReviewEvidence] = {}
    for review in reviews:
        if review.state == "COMMENTED":
            continue
        prior = latest.get(review.login)
        if prior is None or _review_rank(review) >= _review_rank(prior):
            latest[review.login] = review
    return tuple(latest[login] for login in sorted(latest))


def approval_count(
    reviews: Iterable[ReviewEvidence],
    *,
    head_sha: str,
    require_head_match: bool,
) -> int:
    count = 0
    for review in latest_decisive_reviews(reviews):
        if review.state != "APPROVED":
            continue
        if require_head_match and review.commit_id != head_sha:
            continue
        count += 1
    return count


def change_request_count(
    reviews: Iterable[ReviewEvidence],
) -> int:
    return sum(
        review.state == "CHANGES_REQUESTED"
        for review in latest_decisive_reviews(reviews)
    )


def normalize_file(item: Mapping[str, Any]) -> FileEvidence:
    filename = str(item.get("filename") or "").strip()
    if not filename:
        raise EvidenceError("changed-file payload omitted filename")
    return FileEvidence(
        filename=filename,
        status=str(item.get("status") or "unknown"),
        additions=max(0, _int(item.get("additions"))),
        deletions=max(0, _int(item.get("deletions"))),
        changes=max(0, _int(item.get("changes"))),
        previous_filename=(
            str(item.get("previous_filename"))
            if item.get("previous_filename") is not None
            else None
        ),
    )


def sensitive_paths(files: Iterable[FileEvidence]) -> tuple[str, ...]:
    result: set[str] = set()
    for item in files:
        path = item.filename
        if path in SENSITIVE_FILES or path.startswith(SENSITIVE_PREFIXES):
            result.add(path)
        if item.previous_filename:
            previous = item.previous_filename
            if previous in SENSITIVE_FILES or previous.startswith(SENSITIVE_PREFIXES):
                result.add(previous)
    return tuple(sorted(result))


def label_names(pr: Mapping[str, Any]) -> tuple[str, ...]:
    raw = pr.get("labels")
    if not isinstance(raw, list):
        return ()
    names: list[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
    return tuple(sorted(unique_text(names, max_items=1000)))


def _sum_files(files: Sequence[FileEvidence]) -> tuple[int, int]:
    return (
        sum(item.additions for item in files),
        sum(item.deletions for item in files),
    )


def _head_repository(pr: Mapping[str, Any]) -> str | None:
    head = pr.get("head")
    repo = head.get("repo") if isinstance(head, Mapping) else None
    full_name = repo.get("full_name") if isinstance(repo, Mapping) else None
    return str(full_name) if isinstance(full_name, str) and full_name else None


def _author(pr: Mapping[str, Any]) -> str:
    user = pr.get("user")
    login = user.get("login") if isinstance(user, Mapping) else None
    if not isinstance(login, str) or not login.strip():
        raise EvidenceError("pull request omitted author login")
    return login.strip()


def _node_id(pr: Mapping[str, Any]) -> str:
    value = pr.get("node_id")
    if not isinstance(value, str) or not value:
        raise EvidenceError("pull request omitted node_id")
    return value


def _head_base(pr: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    head = pr.get("head")
    base = pr.get("base")
    if not isinstance(head, Mapping) or not isinstance(base, Mapping):
        raise EvidenceError("pull request omitted head/base objects")
    return head, base


class EvidenceCollector:
    """Collect complete mutation-grade evidence for one pull request."""

    def __init__(
        self,
        transport: BudgetedGitHubTransport,
        policy: RunnerPolicy,
    ) -> None:
        self.transport = transport
        self.policy = policy

    def _collect_checks(
        self,
        repository: str,
        head_sha: str,
    ) -> tuple[tuple[CheckEvidence, ...], bool]:
        quoted = quote(head_sha, safe="")
        runs, runs_complete = self.transport.paged_named_list(
            f"/repos/{repository}/commits/{quoted}/check-runs",
            "check_runs",
        )
        statuses, statuses_complete = self.transport.paged_list(
            f"/repos/{repository}/commits/{quoted}/statuses"
        )

        normalized: list[CheckEvidence] = []
        for run in runs:
            item = normalize_check_run(run, expected_head_sha=head_sha)
            if item is not None:
                normalized.append(item)
        for status in statuses:
            item = normalize_status(status, expected_head_sha=head_sha)
            if item is not None:
                normalized.append(item)
        return newest_provider_evidence(normalized), (
            runs_complete and statuses_complete
        )

    def _collect_reviews(
        self,
        repository: str,
        number: int,
    ) -> tuple[tuple[ReviewEvidence, ...], bool]:
        raw, complete = self.transport.paged_list(
            f"/repos/{repository}/pulls/{number}/reviews"
        )
        normalized: list[ReviewEvidence] = []
        for item in raw:
            review = normalize_review(item)
            if review is not None:
                normalized.append(review)
        return tuple(normalized), complete

    def _collect_files(
        self,
        repository: str,
        number: int,
    ) -> tuple[tuple[FileEvidence, ...], bool]:
        max_pages = min(
            self.policy.limits.max_pages,
            max(
                1,
                (self.policy.limits.max_changed_files + 99) // 100,
            ),
        )
        raw, complete = self.transport.paged_list(
            f"/repos/{repository}/pulls/{number}/files",
            max_pages=max_pages,
        )
        if len(raw) > self.policy.limits.max_changed_files:
            raise EvidenceError(
                "changed-file inventory exceeds configured runner limit"
            )
        return tuple(normalize_file(item) for item in raw), complete

    def _collect_threads(
        self,
        repository: str,
        number: int,
    ) -> tuple[int | None, bool]:
        owner, name = repository.split("/", 1)
        cursor: str | None = None
        unresolved = 0
        for _page in range(self.policy.limits.max_pages):
            data = self.transport.graphql(
                THREADS_QUERY,
                {
                    "owner": owner,
                    "name": name,
                    "number": number,
                    "cursor": cursor,
                },
            )
            repository_node = data.get("repository")
            pr = (
                repository_node.get("pullRequest")
                if isinstance(repository_node, Mapping)
                else None
            )
            threads = (
                pr.get("reviewThreads")
                if isinstance(pr, Mapping)
                else None
            )
            if not isinstance(threads, Mapping):
                raise EvidenceError("review-thread GraphQL payload was incomplete")

            nodes = threads.get("nodes")
            if not isinstance(nodes, list):
                raise EvidenceError("review-thread nodes were unavailable")
            for node in nodes:
                if not isinstance(node, Mapping):
                    raise EvidenceError("review-thread node was malformed")
                if node.get("isResolved") is not True:
                    unresolved += 1

            page_info = threads.get("pageInfo")
            if not isinstance(page_info, Mapping):
                raise EvidenceError("review-thread pageInfo was unavailable")
            if page_info.get("hasNextPage") is not True:
                return unresolved, True
            next_cursor = page_info.get("endCursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                return None, False
            cursor = next_cursor
        return None, False

    def _collect_base(
        self,
        repository: str,
        base_ref: str,
    ) -> tuple[str | None, bool, bool | None]:
        try:
            payload = self.transport.get(
                f"/repos/{repository}/branches/{quote(base_ref, safe='')}"
            )
        except RunnerTransportError:
            return None, False, None
        if not isinstance(payload, Mapping):
            return None, False, None
        commit = payload.get("commit")
        sha = commit.get("sha") if isinstance(commit, Mapping) else None
        if not isinstance(sha, str) or not valid_sha(sha.casefold()):
            return None, False, None
        protected = payload.get("protected")
        protected_value = protected if isinstance(protected, bool) else None
        return sha.casefold(), True, protected_value

    def collect(
        self,
        repository: str,
        number: int,
    ) -> RunnerSnapshot:
        if number <= 0:
            raise ValueError("pull-request number must be positive")
        before_requests = self.transport.request_count
        pr = self.transport.get(
            f"/repos/{repository}/pulls/{number}"
        )
        if not isinstance(pr, Mapping):
            raise EvidenceError("pull-request response was not an object")

        head, base = _head_base(pr)
        head_sha = _sha(head.get("sha"), field="head SHA")
        base_sha = _sha(base.get("sha"), field="base SHA")
        base_ref = str(base.get("ref") or "").strip()
        head_ref = str(head.get("ref") or "").strip()
        if not base_ref or not head_ref:
            raise EvidenceError("pull request omitted branch refs")

        checks, checks_complete = self._collect_checks(
            repository,
            head_sha,
        )
        reviews, reviews_complete = self._collect_reviews(
            repository,
            number,
        )
        files, files_complete = self._collect_files(
            repository,
            number,
        )
        thread_count, threads_complete = self._collect_threads(
            repository,
            number,
        )
        base_head_sha, base_complete, protected = self._collect_base(
            repository,
            base_ref,
        )

        check_states = required_check_states(
            checks,
            self.policy.required_checks,
        )
        ci_state = aggregate_ci_state(
            checks,
            self.policy.required_checks,
        )

        additions, deletions = _sum_files(files)
        pr_changed = max(0, _int(pr.get("changed_files")))
        pr_additions = max(0, _int(pr.get("additions")))
        pr_deletions = max(0, _int(pr.get("deletions")))

        # REST PR summary values remain authoritative for line budgets because
        # rename/binary semantics can make file-level arithmetic differ.  A
        # complete file inventory must still contain the advertised file count.
        if files_complete and len(files) != pr_changed:
            files_complete = False

        review_head_required = self.policy.require_latest_reviews_on_head
        approvals = (
            approval_count(
                reviews,
                head_sha=head_sha,
                require_head_match=review_head_required,
            )
            if reviews_complete
            else None
        )
        changes_requested = (
            change_request_count(reviews)
            if reviews_complete
            else None
        )

        head_repo = _head_repository(pr)
        same_repo = (
            head_repo is not None
            and head_repo.casefold() == repository.casefold()
        )

        completeness = EvidenceCompleteness(
            pull_request=True,
            checks=checks_complete,
            statuses=checks_complete,
            reviews=reviews_complete,
            threads=threads_complete,
            files=files_complete,
            base_branch=base_complete,
            base_head=base_complete and base_head_sha is not None,
        )

        core = PRSnapshot(
            repository=repository,
            number=number,
            head_sha=head_sha,
            base_sha=base_sha,
            base_ref=base_ref,
            head_ref=head_ref,
            state=str(pr.get("state") or "unknown"),
            merged=pr.get("merged") is True,
            draft=pr.get("draft") is True,
            from_fork=not same_repo,
            mergeable=(
                pr.get("mergeable")
                if isinstance(pr.get("mergeable"), bool)
                else None
            ),
            mergeable_state=str(
                pr.get("mergeable_state") or "unknown"
            ),
            ci_state=(
                ci_state
                if checks_complete
                else CIState.UNKNOWN
            ),
            approvals=approvals,
            changes_requested=changes_requested,
            unresolved_threads=(
                thread_count
                if threads_complete
                else None
            ),
            changed_files=pr_changed,
            additions=pr_additions,
            deletions=pr_deletions,
            sensitive_paths=(
                sensitive_paths(files)
                if files_complete
                else None
            ),
            labels=label_names(pr),
            updated_at=(
                str(pr.get("updated_at"))
                if pr.get("updated_at") is not None
                else None
            ),
        )

        if protected is False and self.policy.protected_base_required:
            # Protection is an execution precondition rather than a core policy
            # field.  Preserve the evidence in the snapshot through a label-like
            # completeness signal; transaction code will block mutation.
            pass

        captured = utcnow().isoformat()
        after_requests = self.transport.request_count
        return RunnerSnapshot(
            core=core,
            pr_node_id=_node_id(pr),
            author=_author(pr),
            head_repository=head_repo,
            base_head_sha=base_head_sha,
            labels=core.labels,
            files=files,
            checks=checks,
            reviews=reviews,
            required_check_states=check_states,
            completeness=completeness,
            captured_at=captured,
            source_request_count=max(0, after_requests - before_requests),
            etag=None,
        )

    def refresh_policy_fields(
        self,
        prior: RunnerSnapshot,
    ) -> RunnerSnapshot:
        """Collect a complete fresh snapshot for mutation-boundary comparison."""
        return self.collect(prior.core.repository, prior.core.number)


def snapshot_incomplete_reasons(
    snapshot: RunnerSnapshot,
) -> tuple[str, ...]:
    reasons = [
        f"evidence_incomplete:{name}"
        for name in snapshot.completeness.missing()
    ]
    return tuple(reasons)


def check_state_map(
    snapshot: RunnerSnapshot,
) -> dict[str, CheckState]:
    return dict(snapshot.required_check_states)


def failing_required_checks(
    snapshot: RunnerSnapshot,
) -> tuple[str, ...]:
    return tuple(
        name
        for name, state in snapshot.required_check_states
        if state in {CheckState.FAILING, CheckState.CANCELLED}
    )


def pending_required_checks(
    snapshot: RunnerSnapshot,
) -> tuple[str, ...]:
    return tuple(
        name
        for name, state in snapshot.required_check_states
        if state is CheckState.PENDING
    )


def missing_required_checks(
    snapshot: RunnerSnapshot,
) -> tuple[str, ...]:
    return tuple(
        name
        for name, state in snapshot.required_check_states
        if state in {CheckState.MISSING, CheckState.UNKNOWN, CheckState.SKIPPED}
    )


def stale_reviewers(
    snapshot: RunnerSnapshot,
) -> tuple[str, ...]:
    if not snapshot.core.head_sha:
        return ()
    return tuple(
        review.login
        for review in latest_decisive_reviews(snapshot.reviews)
        if review.state == "APPROVED"
        and review.commit_id != snapshot.core.head_sha
    )


def snapshot_diagnostics(
    snapshot: RunnerSnapshot,
) -> Mapping[str, Any]:
    return {
        "repository": snapshot.core.repository,
        "pr_number": snapshot.core.number,
        "head_sha": snapshot.core.head_sha,
        "base_sha": snapshot.core.base_sha,
        "base_head_sha": snapshot.base_head_sha,
        "exact_base_head": snapshot.exact_base_head,
        "same_repository_head": snapshot.same_repository_head,
        "author": snapshot.author,
        "ci_state": snapshot.core.ci_state.value,
        "required_checks": {
            name: state.value
            for name, state in snapshot.required_check_states
        },
        "approvals": snapshot.core.approvals,
        "changes_requested": snapshot.core.changes_requested,
        "unresolved_threads": snapshot.core.unresolved_threads,
        "changed_files": snapshot.core.changed_files,
        "additions": snapshot.core.additions,
        "deletions": snapshot.core.deletions,
        "sensitive_paths": snapshot.core.sensitive_paths,
        "completeness": {
            key: value
            for key, value in snapshot.completeness.__dict__.items()
        }
        if hasattr(snapshot.completeness, "__dict__")
        else {
            "pull_request": snapshot.completeness.pull_request,
            "checks": snapshot.completeness.checks,
            "statuses": snapshot.completeness.statuses,
            "reviews": snapshot.completeness.reviews,
            "threads": snapshot.completeness.threads,
            "files": snapshot.completeness.files,
            "base_branch": snapshot.completeness.base_branch,
            "base_head": snapshot.completeness.base_head,
        },
        "source_request_count": snapshot.source_request_count,
        "captured_at": snapshot.captured_at,
    }


__all__ = [
    "EvidenceCollector",
    "EvidenceError",
    "SENSITIVE_FILES",
    "SENSITIVE_PREFIXES",
    "THREADS_QUERY",
    "aggregate_ci_state",
    "approval_count",
    "change_request_count",
    "check_state_map",
    "failing_required_checks",
    "label_names",
    "latest_decisive_reviews",
    "missing_required_checks",
    "newest_provider_evidence",
    "normalize_check_run",
    "normalize_file",
    "normalize_review",
    "normalize_status",
    "pending_required_checks",
    "reduce_context_state",
    "required_check_states",
    "sensitive_paths",
    "snapshot_diagnostics",
    "snapshot_incomplete_reasons",
    "stale_reviewers",
]
