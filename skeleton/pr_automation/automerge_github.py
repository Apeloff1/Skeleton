"""GitHub transport adapter for the auto-merge control plane.

All privileged reads and mutations are centralized here so the policy and engine
remain deterministic.  The adapter uses bounded pagination, bounded retries,
strict payload validation, and expected-head SHA binding for merge mutations.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .automerge_model import (
    CandidateSnapshot,
    DiffSummary,
    MergeMethod,
    MutationReceipt,
    PullRequestIdentity,
    ReviewEvidence,
    WorkflowEvidence,
    valid_sha,
)


API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"


class AutoMergeGitHubError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CompareResult:
    status: str
    ahead_by: int
    behind_by: int

    @property
    def head_contains_base(self) -> bool:
        return self.behind_by == 0


@dataclass(frozen=True, slots=True)
class BranchPolicy:
    protected: bool
    required_status_contexts: tuple[str, ...]
    required_approvals: int | None
    requires_conversation_resolution: bool | None


class GitHubAutoMergeClient:
    def __init__(
        self,
        token: str,
        repository: str,
        *,
        retries: int = 3,
        timeout: int = 30,
        max_pages: int = 10,
    ) -> None:
        if not token:
            raise ValueError("GitHub token is required")
        if repository.count("/") != 1:
            raise ValueError("repository must be owner/name")
        if isinstance(retries, bool) or retries < 0 or retries > 10:
            raise ValueError("retries must be between 0 and 10")
        if isinstance(timeout, bool) or timeout <= 0 or timeout > 120:
            raise ValueError("timeout must be between 1 and 120 seconds")
        if isinstance(max_pages, bool) or max_pages <= 0 or max_pages > 100:
            raise ValueError("max_pages must be between 1 and 100")
        self.token = token
        self.repository = repository
        self.retries = retries
        self.timeout = timeout
        self.max_pages = max_pages

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "skeleton-automerge-control-plane/1",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def request(
        self,
        method: str,
        url: str,
        body: Mapping[str, Any] | None = None,
    ) -> Any:
        encoded = None if body is None else json.dumps(dict(body)).encode("utf-8")
        headers = self._headers()
        if encoded is not None:
            headers["Content-Type"] = "application/json"

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            request = Request(
                url,
                data=encoded,
                headers=headers,
                method=method,
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = response.read()
                    if not payload:
                        return None
                    text = payload.decode("utf-8")
                    return json.loads(text)
            except HTTPError as exc:
                last_error = exc
                retry_after = exc.headers.get("Retry-After")
                remaining = exc.headers.get("X-RateLimit-Remaining")
                reset = exc.headers.get("X-RateLimit-Reset")
                retryable = (
                    exc.code in {429, 500, 502, 503, 504}
                    or remaining == "0"
                    or (exc.code == 403 and bool(retry_after))
                )
                if not retryable or attempt >= self.retries:
                    detail = exc.read().decode("utf-8", errors="replace")[:2000]
                    raise AutoMergeGitHubError(
                        f"GitHub HTTP {exc.code}: {detail}"
                    ) from exc
                if retry_after and retry_after.isdigit():
                    delay = min(30, max(1, int(retry_after)))
                elif remaining == "0" and reset and reset.isdigit():
                    delay = min(30, max(1, int(reset) - int(time.time())))
                else:
                    delay = min(8, 2**attempt)
                time.sleep(delay)
            except (URLError, TimeoutError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise AutoMergeGitHubError(f"GitHub request failed: {exc}") from exc
                time.sleep(min(8, 2**attempt))
        raise AutoMergeGitHubError(f"GitHub request failed: {last_error}")

    def get(self, path: str) -> Any:
        return self.request("GET", f"{API}{path}")

    def post(self, path: str, body: Mapping[str, Any] | None = None) -> Any:
        return self.request("POST", f"{API}{path}", body)

    def put(self, path: str, body: Mapping[str, Any] | None = None) -> Any:
        return self.request("PUT", f"{API}{path}", body)

    def patch(self, path: str, body: Mapping[str, Any] | None = None) -> Any:
        return self.request("PATCH", f"{API}{path}", body)

    def graphql(self, query: str, variables: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = self.request(
            "POST",
            GRAPHQL,
            {"query": query, "variables": dict(variables)},
        )
        if not isinstance(payload, Mapping):
            raise AutoMergeGitHubError("GraphQL response was not an object")
        if payload.get("errors"):
            raise AutoMergeGitHubError(
                f"GraphQL returned errors: {payload.get('errors')!r}"
            )
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise AutoMergeGitHubError("GraphQL response omitted data")
        return data

    def _paginate_list(self, path: str, *, per_page: int = 100) -> list[Any]:
        output: list[Any] = []
        separator = "&" if "?" in path else "?"
        for page in range(1, self.max_pages + 1):
            payload = self.get(
                f"{path}{separator}{urlencode({'per_page': per_page, 'page': page})}"
            )
            if not isinstance(payload, list):
                raise AutoMergeGitHubError(f"expected list payload for {path}")
            output.extend(payload)
            if len(payload) < per_page:
                return output
        raise AutoMergeGitHubError(
            f"bounded pagination exceeded {self.max_pages} pages for {path}"
        )

    def _paginate_runs(self, path: str, *, per_page: int = 100) -> list[Mapping[str, Any]]:
        output: list[Mapping[str, Any]] = []
        separator = "&" if "?" in path else "?"
        for page in range(1, self.max_pages + 1):
            payload = self.get(
                f"{path}{separator}{urlencode({'per_page': per_page, 'page': page})}"
            )
            if not isinstance(payload, Mapping):
                raise AutoMergeGitHubError("workflow-run payload was not an object")
            batch = payload.get("workflow_runs")
            if not isinstance(batch, list):
                raise AutoMergeGitHubError("workflow-run payload omitted workflow_runs")
            output.extend(item for item in batch if isinstance(item, Mapping))
            if len(batch) < per_page:
                return output
        raise AutoMergeGitHubError(
            f"bounded workflow pagination exceeded {self.max_pages} pages"
        )

    def branch_head(self, branch: str) -> str:
        payload = self.get(
            f"/repos/{self.repository}/branches/{quote(branch, safe='')}"
        )
        commit = payload.get("commit") if isinstance(payload, Mapping) else None
        sha = commit.get("sha") if isinstance(commit, Mapping) else None
        if not isinstance(sha, str) or not valid_sha(sha):
            raise AutoMergeGitHubError("branch head was missing or non-canonical")
        return sha

    def open_pull_requests(self, *, limit: int = 250) -> list[Mapping[str, Any]]:
        if isinstance(limit, bool) or limit <= 0 or limit > 1000:
            raise ValueError("open PR limit must be between 1 and 1000")
        out: list[Mapping[str, Any]] = []
        for page in range(1, min(self.max_pages, (limit + 99) // 100) + 1):
            query = urlencode(
                {
                    "state": "open",
                    "sort": "updated",
                    "direction": "asc",
                    "per_page": min(100, limit - len(out)),
                    "page": page,
                }
            )
            payload = self.get(f"/repos/{self.repository}/pulls?{query}")
            if not isinstance(payload, list):
                raise AutoMergeGitHubError("open PR inventory was not a list")
            out.extend(item for item in payload if isinstance(item, Mapping))
            if len(out) >= limit or len(payload) < 100:
                break
        return out[:limit]

    def pull_request(self, number: int) -> Mapping[str, Any]:
        payload = self.get(f"/repos/{self.repository}/pulls/{number}")
        if not isinstance(payload, Mapping):
            raise AutoMergeGitHubError("pull request payload was not an object")
        return payload

    def _identity(self, payload: Mapping[str, Any]) -> PullRequestIdentity:
        head = payload.get("head")
        base = payload.get("base")
        user = payload.get("user")
        if not isinstance(head, Mapping) or not isinstance(base, Mapping):
            raise AutoMergeGitHubError("pull request omitted head/base identity")
        if not isinstance(user, Mapping):
            raise AutoMergeGitHubError("pull request omitted author identity")

        head_repo = head.get("repo")
        if not isinstance(head_repo, Mapping):
            raise AutoMergeGitHubError("pull request head repository unavailable")

        return PullRequestIdentity(
            repository=self.repository,
            number=int(payload.get("number") or 0),
            node_id=str(payload.get("node_id") or ""),
            state=str(payload.get("state") or ""),
            draft=payload.get("draft") is True,
            author=str(user.get("login") or ""),
            base_ref=str(base.get("ref") or ""),
            base_sha=str(base.get("sha") or ""),
            head_ref=str(head.get("ref") or ""),
            head_sha=str(head.get("sha") or ""),
            head_repo=str(head_repo.get("full_name") or ""),
            mergeable=payload.get("mergeable"),
            mergeable_state=str(payload.get("mergeable_state") or "unknown"),
            created_at=(
                str(payload.get("created_at"))
                if payload.get("created_at") is not None
                else None
            ),
            updated_at=(
                str(payload.get("updated_at"))
                if payload.get("updated_at") is not None
                else None
            ),
        )

    def changed_files(self, number: int) -> tuple[DiffSummary, tuple[Mapping[str, Any], ...]]:
        items = self._paginate_list(
            f"/repos/{self.repository}/pulls/{number}/files"
        )
        files: list[str] = []
        additions = 0
        deletions = 0
        normalized_items: list[Mapping[str, Any]] = []
        for item in items:
            if not isinstance(item, Mapping):
                raise AutoMergeGitHubError("malformed changed-file entry")
            filename = item.get("filename")
            if not isinstance(filename, str) or not filename:
                raise AutoMergeGitHubError("changed-file entry omitted filename")
            files.append(filename)
            additions += int(item.get("additions") or 0)
            deletions += int(item.get("deletions") or 0)
            normalized_items.append(item)
        return (
            DiffSummary(
                files=tuple(files),
                additions=additions,
                deletions=deletions,
                changed_files=len(files),
            ),
            tuple(normalized_items),
        )

    def labels(self, payload: Mapping[str, Any]) -> tuple[str, ...]:
        labels = payload.get("labels")
        if not isinstance(labels, list):
            return ()
        out: list[str] = []
        for item in labels:
            if isinstance(item, Mapping) and isinstance(item.get("name"), str):
                out.append(item["name"])
        return tuple(dict.fromkeys(out))

    def reviews(self, number: int) -> tuple[ReviewEvidence, ...]:
        items = self._paginate_list(
            f"/repos/{self.repository}/pulls/{number}/reviews"
        )
        out: list[ReviewEvidence] = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            user = item.get("user")
            login = user.get("login") if isinstance(user, Mapping) else None
            if not isinstance(login, str) or not login:
                continue
            out.append(
                ReviewEvidence(
                    login=login,
                    state=str(item.get("state") or ""),
                    submitted_at=(
                        str(item.get("submitted_at"))
                        if item.get("submitted_at") is not None
                        else None
                    ),
                    commit_id=(
                        str(item.get("commit_id"))
                        if item.get("commit_id") is not None
                        else None
                    ),
                )
            )
        return tuple(out)

    def unresolved_threads(self, number: int) -> int:
        query = """
        query($owner:String!,$name:String!,$number:Int!,$cursor:String) {
          repository(owner:$owner,name:$name) {
            pullRequest(number:$number) {
              reviewThreads(first:100,after:$cursor) {
                nodes { isResolved }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }
        """
        owner, name = self.repository.split("/", 1)
        cursor: str | None = None
        unresolved = 0
        for _page in range(self.max_pages):
            data = self.graphql(
                query,
                {
                    "owner": owner,
                    "name": name,
                    "number": number,
                    "cursor": cursor,
                },
            )
            repository = data.get("repository")
            pr = repository.get("pullRequest") if isinstance(repository, Mapping) else None
            threads = pr.get("reviewThreads") if isinstance(pr, Mapping) else None
            if not isinstance(threads, Mapping):
                raise AutoMergeGitHubError("review thread payload missing")
            nodes = threads.get("nodes")
            if not isinstance(nodes, list):
                raise AutoMergeGitHubError("review thread nodes missing")
            for node in nodes:
                if isinstance(node, Mapping) and node.get("isResolved") is not True:
                    unresolved += 1
            page_info = threads.get("pageInfo")
            if not isinstance(page_info, Mapping):
                raise AutoMergeGitHubError("review thread pageInfo missing")
            if page_info.get("hasNextPage") is not True:
                return unresolved
            next_cursor = page_info.get("endCursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                raise AutoMergeGitHubError("review thread pagination cursor missing")
            cursor = next_cursor
        raise AutoMergeGitHubError("review thread pagination exceeded bound")

    def workflow_runs(self, head_sha: str) -> tuple[WorkflowEvidence, ...]:
        if not valid_sha(head_sha):
            raise ValueError("head_sha must be canonical lowercase SHA")
        query = urlencode({"head_sha": head_sha})
        items = self._paginate_runs(
            f"/repos/{self.repository}/actions/runs?{query}"
        )
        out: list[WorkflowEvidence] = []
        for item in items:
            name = item.get("name")
            event = item.get("event")
            status = item.get("status")
            sha = item.get("head_sha")
            if not all(isinstance(value, str) and value for value in (name, event, status, sha)):
                continue
            if not valid_sha(sha):
                continue
            out.append(
                WorkflowEvidence(
                    name=name,
                    run_id=int(item.get("id") or 0),
                    run_number=int(item.get("run_number") or 0),
                    attempt=int(item.get("run_attempt") or 0),
                    head_sha=sha,
                    event=event,
                    status=status,
                    conclusion=(
                        str(item.get("conclusion"))
                        if item.get("conclusion") is not None
                        else None
                    ),
                    created_at=(
                        str(item.get("created_at"))
                        if item.get("created_at") is not None
                        else None
                    ),
                    updated_at=(
                        str(item.get("updated_at"))
                        if item.get("updated_at") is not None
                        else None
                    ),
                    html_url=(
                        str(item.get("html_url"))
                        if item.get("html_url") is not None
                        else None
                    ),
                )
            )
        return tuple(out)

    def compare(self, base_sha: str, head_sha: str) -> CompareResult:
        if not valid_sha(base_sha) or not valid_sha(head_sha):
            raise ValueError("compare SHAs must be canonical lowercase SHAs")
        payload = self.get(
            f"/repos/{self.repository}/compare/{base_sha}...{head_sha}"
        )
        if not isinstance(payload, Mapping):
            raise AutoMergeGitHubError("compare payload was not an object")
        return CompareResult(
            status=str(payload.get("status") or ""),
            ahead_by=int(payload.get("ahead_by") or 0),
            behind_by=int(payload.get("behind_by") or 0),
        )

    def snapshot(self, number: int) -> CandidateSnapshot:
        payload = self.pull_request(number)
        identity = self._identity(payload)
        diff, _items = self.changed_files(number)
        reviews = self.reviews(number)
        unresolved = self.unresolved_threads(number)
        runs = self.workflow_runs(identity.head_sha)
        compare = self.compare(identity.base_sha, identity.head_sha)
        return CandidateSnapshot(
            identity=identity,
            diff=diff,
            labels=self.labels(payload),
            reviews=reviews,
            unresolved_threads=unresolved,
            workflow_runs=runs,
            head_contains_base=compare.head_contains_base,
        )

    def snapshots(self, *, limit: int = 250) -> tuple[CandidateSnapshot, ...]:
        summaries = self.open_pull_requests(limit=limit)
        out: list[CandidateSnapshot] = []
        for item in summaries:
            number = item.get("number")
            if not isinstance(number, int) or number <= 0:
                raise AutoMergeGitHubError("open PR inventory contains invalid number")
            out.append(self.snapshot(number))
        return tuple(out)

    def merge(
        self,
        number: int,
        *,
        expected_head_sha: str,
        method: MergeMethod,
    ) -> MutationReceipt:
        if not valid_sha(expected_head_sha):
            raise ValueError("expected_head_sha must be canonical lowercase SHA")
        payload = self.put(
            f"/repos/{self.repository}/pulls/{number}/merge",
            {
                "sha": expected_head_sha,
                "merge_method": method.value,
            },
        )
        if not isinstance(payload, Mapping):
            raise AutoMergeGitHubError("merge response was not an object")
        merged = payload.get("merged") is True
        merge_sha = payload.get("sha")
        if merge_sha is not None and not isinstance(merge_sha, str):
            merge_sha = None
        current = self.pull_request(number)
        current_identity = self._identity(current)
        return MutationReceipt(
            pr_number=number,
            action_key=f"merge:{number}:{expected_head_sha}:{method.value}",
            requested_head_sha=expected_head_sha,
            observed_head_sha=current_identity.head_sha,
            base_ref=current_identity.base_ref,
            merged=merged,
            merge_sha=merge_sha,
            message=str(payload.get("message") or ""),
        )

    def enable_native_auto_merge(
        self,
        number: int,
        *,
        expected_head_sha: str,
        method: MergeMethod,
    ) -> MutationReceipt:
        query = """
        mutation($pullRequestId:ID!,$mergeMethod:PullRequestMergeMethod!) {
          enablePullRequestAutoMerge(input:{
            pullRequestId:$pullRequestId,
            mergeMethod:$mergeMethod
          }) {
            pullRequest { number headRefOid baseRefName autoMergeRequest { enabledAt } }
          }
        }
        """
        current = self.pull_request(number)
        identity = self._identity(current)
        if identity.head_sha != expected_head_sha:
            return MutationReceipt(
                pr_number=number,
                action_key=f"native:{number}:{expected_head_sha}:{method.value}",
                requested_head_sha=expected_head_sha,
                observed_head_sha=identity.head_sha,
                base_ref=identity.base_ref,
                merged=False,
                merge_sha=None,
                message="head moved before native auto-merge enable",
            )
        method_map = {
            MergeMethod.SQUASH: "SQUASH",
            MergeMethod.MERGE: "MERGE",
            MergeMethod.REBASE: "REBASE",
        }
        self.graphql(
            query,
            {
                "pullRequestId": identity.node_id,
                "mergeMethod": method_map[method],
            },
        )
        after = self.pull_request(number)
        after_identity = self._identity(after)
        return MutationReceipt(
            pr_number=number,
            action_key=f"native:{number}:{expected_head_sha}:{method.value}",
            requested_head_sha=expected_head_sha,
            observed_head_sha=after_identity.head_sha,
            base_ref=after_identity.base_ref,
            merged=str(after.get("state") or "").casefold() == "closed"
            and after.get("merged") is True,
            merge_sha=(
                str(after.get("merge_commit_sha"))
                if after.get("merge_commit_sha") is not None
                else None
            ),
            message="native auto-merge enabled",
        )

    def update_base(self, number: int, *, base_ref: str) -> PullRequestIdentity:
        payload = self.patch(
            f"/repos/{self.repository}/pulls/{number}",
            {"base": base_ref},
        )
        if not isinstance(payload, Mapping):
            raise AutoMergeGitHubError("base update response was not an object")
        return self._identity(payload)

    def dispatch_workflow(
        self,
        workflow_file: str,
        *,
        ref: str,
        inputs: Mapping[str, str] | None = None,
    ) -> None:
        self.post(
            f"/repos/{self.repository}/actions/workflows/{quote(workflow_file, safe='')}/dispatches",
            {"ref": ref, "inputs": dict(inputs or {})},
        )

    def branch_policy(self, branch: str) -> BranchPolicy:
        encoded = quote(branch, safe="")
        payload = self.get(
            f"/repos/{self.repository}/branches/{encoded}"
        )
        if not isinstance(payload, Mapping):
            raise AutoMergeGitHubError("branch payload was not an object")
        protected = payload.get("protected") is True
        if not protected:
            return BranchPolicy(
                protected=False,
                required_status_contexts=(),
                required_approvals=None,
                requires_conversation_resolution=None,
            )

        try:
            protection = self.get(
                f"/repos/{self.repository}/branches/{encoded}/protection"
            )
        except AutoMergeGitHubError:
            return BranchPolicy(
                protected=True,
                required_status_contexts=(),
                required_approvals=None,
                requires_conversation_resolution=None,
            )
        if not isinstance(protection, Mapping):
            raise AutoMergeGitHubError("branch protection payload was not an object")
        checks = protection.get("required_status_checks")
        contexts: tuple[str, ...] = ()
        if isinstance(checks, Mapping):
            raw = checks.get("contexts")
            if isinstance(raw, list):
                contexts = tuple(str(item) for item in raw if isinstance(item, str))

        reviews = protection.get("required_pull_request_reviews")
        approvals: int | None = None
        if isinstance(reviews, Mapping):
            value = reviews.get("required_approving_review_count")
            if isinstance(value, int) and not isinstance(value, bool):
                approvals = value

        conversation = protection.get("required_conversation_resolution")
        requires_resolution: bool | None = None
        if isinstance(conversation, Mapping):
            requires_resolution = conversation.get("enabled") is True

        return BranchPolicy(
            protected=True,
            required_status_contexts=contexts,
            required_approvals=approvals,
            requires_conversation_resolution=requires_resolution,
        )

    def repository_auto_merge_allowed(self) -> bool:
        payload = self.get(f"/repos/{self.repository}")
        if not isinstance(payload, Mapping):
            raise AutoMergeGitHubError("repository payload was not an object")
        return payload.get("allow_auto_merge") is True

    def rerun_failed(self, run_id: int) -> None:
        if isinstance(run_id, bool) or run_id <= 0:
            raise ValueError("run_id must be positive")
        self.post(
            f"/repos/{self.repository}/actions/runs/{run_id}/rerun-failed-jobs"
        )

    def cancel_run(self, run_id: int) -> None:
        if isinstance(run_id, bool) or run_id <= 0:
            raise ValueError("run_id must be positive")
        self.post(
            f"/repos/{self.repository}/actions/runs/{run_id}/cancel"
        )


__all__ = [
    "AutoMergeGitHubError",
    "BranchPolicy",
    "CompareResult",
    "GitHubAutoMergeClient",
]
