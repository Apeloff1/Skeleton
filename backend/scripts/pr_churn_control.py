"""Bounded, fail-closed cleanup for trusted pull-request churn.

Ordinary PR retirement still requires explicit supersedence from a newer trusted
same-repository PR. The only additional retirement class is the exact automated
reverse-sync template that uses the default branch as head to refresh a
non-protected feature branch; this class is matched by full identity, title, and
body contract rather than by loose heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Iterable

PAGE_SIZE = 100
MAX_OPEN_PAGES = 50
DEFAULT_MAX_MUTATIONS = 100
ABSOLUTE_MAX_MUTATIONS = 250
PRESERVE_LABELS = frozenset({"churn/preserve", "keep-open", "do-not-close"})
_RETRYABLE = frozenset({0, 429, 500, 502, 503, 504})
_SUPERSEDES_DIRECTIVE_RE = re.compile(
    r"^\s*(?:(?:[-*+]\s+)|(?:#{1,6}\s+))?supersedes\b", re.IGNORECASE
)
_PR_REF_RE = re.compile(r"#([1-9][0-9]*)\b")
_SYNC_TITLE_PREFIX = "chore(sync): refresh "
_PROTECTED_SYNC_BASES = frozenset(
    {"main", "master", "develop", "development", "staging", "production", "prod", "gh-pages"}
)


@dataclass(frozen=True, slots=True)
class Retirement:
    source_number: int
    target_number: int


@dataclass(frozen=True, slots=True)
class ReverseSyncRetirement:
    number: int


class GitHubApi:
    def __init__(self, token: str, *, sleep: Callable[[float], None] = time.sleep):
        self._token = token
        self._sleep = sleep
        self._api = "https://api.github.com"
        self._headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "skeleton-pr-churn-controller",
        }

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        data = None
        headers = dict(self._headers)
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif method != "GET":
            data = b""

        req = urllib.request.Request(
            self._api + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read()
                body = json.loads(raw) if raw else None
                return response.status, body, dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
                body = json.loads(raw) if raw else None
            except (OSError, ValueError):
                body = None
            return exc.code, body, dict(exc.headers.items()) if exc.headers else {}
        except urllib.error.URLError:
            return 0, None, {}

    def sleep(self, seconds: float) -> None:
        self._sleep(seconds)


def _retryable(status: int, payload: Any) -> bool:
    if status in _RETRYABLE:
        return True
    if status != 403:
        return False
    message = str((payload or {}).get("message") or "").lower()
    return "rate limit" in message or "abuse" in message


def _request_with_retry(
    api: GitHubApi,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    attempts: int = 3,
) -> tuple[int, Any, dict[str, str]]:
    status = 0
    body: Any = None
    headers: dict[str, str] = {}
    for attempt in range(attempts):
        status, body, headers = api.request(path, method=method, payload=payload)
        if not _retryable(status, body):
            return status, body, headers
        if attempt + 1 < attempts:
            retry_after = headers.get("Retry-After") or headers.get("retry-after")
            if retry_after:
                try:
                    delay = max(0.0, min(float(retry_after), 30.0))
                except ValueError:
                    delay = float(2**attempt)
            else:
                delay = float(2**attempt)
            api.sleep(delay)
    return status, body, headers


def _repo_full_name(value: Any) -> str:
    return str((value or {}).get("full_name") or "")


def _author_login(pr: dict[str, Any]) -> str:
    return str((pr.get("user") or {}).get("login") or "")


def _label_names(pr: dict[str, Any]) -> set[str]:
    labels = pr.get("labels") or []
    names: set[str] = set()
    for label in labels:
        if isinstance(label, dict) and label.get("name"):
            names.add(str(label["name"]).strip().lower())
    return names


def _is_protected_sync_base(ref: str) -> bool:
    normalized = ref.strip()
    return normalized in _PROTECTED_SYNC_BASES or normalized.startswith(
        ("release/", "keep/", "backup/", "archive/")
    )


def eligible_reverse_sync(
    pr: dict[str, Any],
    *,
    repo: str,
    default_branch: str,
    trusted_author: str,
) -> tuple[bool, str]:
    """Return whether an automation-created reverse sync PR may be retired.

    This is intentionally narrower than title-pattern matching. The PR must be
    owner-authored, same-repository, use the default branch as its head, target
    a non-protected non-default branch, and match the exact automation title
    and body templates. Ordinary feature/release PRs are therefore out of
    scope even when they happen to merge the default branch into another ref.
    """
    if int(pr.get("number") or 0) <= 0:
        return False, "sync PR has invalid identity"
    if str(pr.get("state") or "").lower() != "open":
        return False, "sync PR is not open"
    if bool(pr.get("draft")):
        return False, "sync PR is draft"
    if bool(pr.get("merged")) or pr.get("merged_at"):
        return False, "sync PR is already merged"
    if _author_login(pr).lower() != trusted_author.lower():
        return False, "sync PR author is not trusted"
    if _label_names(pr) & PRESERVE_LABELS:
        return False, "sync PR carries an explicit preserve label"

    head = pr.get("head") or {}
    base = pr.get("base") or {}
    if _repo_full_name(head.get("repo")) != repo:
        return False, "sync PR head is not same-repository"
    if _repo_full_name(base.get("repo")) != repo:
        return False, "sync PR base is not same-repository"

    head_ref = str(head.get("ref") or "")
    base_ref = str(base.get("ref") or "")
    if head_ref != default_branch:
        return False, "sync PR head is not the default branch"
    if not base_ref or base_ref == default_branch:
        return False, "sync PR does not target a non-default branch"
    if _is_protected_sync_base(base_ref):
        return False, "sync PR targets a protected long-lived branch"

    expected_title = f"{_SYNC_TITLE_PREFIX}{base_ref} from {default_branch}"
    if str(pr.get("title") or "").strip() != expected_title:
        return False, "sync PR title does not match the automation contract"

    expected_body = (
        f"Automated stale-branch refresh. Merge current `{default_branch}` "
        "into this branch without rewriting branch history."
    )
    if str(pr.get("body") or "").strip() != expected_body:
        return False, "sync PR body does not match the automation contract"

    return True, "exact trusted reverse-sync automation"


def _trusted_open_source(
    pr: dict[str, Any],
    *,
    repo: str,
    default_branch: str,
    trusted_author: str,
) -> bool:
    if str(pr.get("state") or "").lower() != "open":
        return False
    if bool(pr.get("draft")):
        return False
    if int(pr.get("number") or 0) <= 0:
        return False
    if _author_login(pr).lower() != trusted_author.lower():
        return False
    if str((pr.get("base") or {}).get("ref") or "") != default_branch:
        return False
    if _repo_full_name((pr.get("head") or {}).get("repo")) != repo:
        return False
    title = str(pr.get("title") or "").strip().lower()
    if title.startswith("[validation]"):
        return False
    return True


def _strip_untrusted_markdown_regions(body: str) -> Iterable[str]:
    """Yield ordinary prose lines, excluding fenced code and blockquotes."""
    fenced = False
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or line.lstrip().startswith(">"):
            continue
        yield line


def superseded_numbers(body: object) -> tuple[int, ...]:
    """Extract explicit ``Supersedes ... #N`` directive lines.

    The directive must begin the prose line (optionally after a Markdown list or
    heading marker). This deliberately rejects incidental or negated prose such
    as ``does not supersede #10``. Multiple references in the same directive are
    supported. Fenced code and blockquotes are ignored.
    """
    if not isinstance(body, str) or not body.strip():
        return ()

    found: list[int] = []
    seen: set[int] = set()
    for line in _strip_untrusted_markdown_regions(body):
        match = _SUPERSEDES_DIRECTIVE_RE.match(line)
        if match is None:
            continue
        tail = line[match.end() : match.end() + 180]
        clause = re.split(r"[.!?;]", tail, maxsplit=1)[0]
        for ref in _PR_REF_RE.finditer(clause):
            number = int(ref.group(1))
            if number not in seen:
                seen.add(number)
                found.append(number)
    return tuple(found)


def _newer_than(source: dict[str, Any], target: dict[str, Any]) -> bool:
    source_number = int(source.get("number") or 0)
    target_number = int(target.get("number") or 0)
    if source_number <= target_number:
        return False
    source_created = str(source.get("created_at") or "")
    target_created = str(target.get("created_at") or "")
    if not source_created or not target_created:
        return False
    return source_created > target_created


def eligible_pair(
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    repo: str,
    default_branch: str,
    trusted_author: str,
) -> tuple[bool, str]:
    """Return whether ``source`` may explicitly retire ``target``."""
    if not _trusted_open_source(
        source,
        repo=repo,
        default_branch=default_branch,
        trusted_author=trusted_author,
    ):
        return False, "source is not an active trusted same-repository PR"

    source_number = int(source.get("number") or 0)
    target_number = int(target.get("number") or 0)
    if not target_number or target_number == source_number:
        return False, "invalid or self-referential target"
    if target_number not in superseded_numbers(source.get("body")):
        return False, "source does not explicitly supersede target"

    if str(target.get("state") or "").lower() != "open":
        return False, "target is not open"
    if bool(target.get("merged")) or target.get("merged_at"):
        return False, "target is already merged"
    if _author_login(target).lower() != trusted_author.lower():
        return False, "target author is not trusted"
    if str((target.get("base") or {}).get("ref") or "") != default_branch:
        return False, "target does not use the default base"
    if _repo_full_name((target.get("head") or {}).get("repo")) != repo:
        return False, "target is not same-repository"
    if _label_names(target) & PRESERVE_LABELS:
        return False, "target carries an explicit preserve label"
    if not _newer_than(source, target):
        return False, "source is not newer than target"

    return True, "explicit trusted supersedence"


def list_open_prs(
    api: GitHubApi,
    *,
    repo: str,
    default_branch: str,
) -> list[dict[str, Any]]:
    prs: list[dict[str, Any]] = []
    for page in range(1, MAX_OPEN_PAGES + 1):
        query = urllib.parse.urlencode(
            {
                "state": "open",
                "sort": "created",
                "direction": "desc",
                "per_page": PAGE_SIZE,
                "page": page,
            }
        )
        status, payload, _ = _request_with_retry(
            api, f"/repos/{repo}/pulls?{query}"
        )
        if status != 200 or not isinstance(payload, list):
            raise RuntimeError(f"failed to list open pull requests: HTTP {status}")
        prs.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < PAGE_SIZE:
            return prs
    raise RuntimeError(
        f"open pull-request scan exceeded bounded {MAX_OPEN_PAGES * PAGE_SIZE}-entry window"
    )


def build_retirement_plan(
    prs: Iterable[dict[str, Any]],
    *,
    repo: str,
    default_branch: str,
    trusted_author: str,
    max_mutations: int,
) -> list[Retirement]:
    """Build a deterministic newest-source-wins retirement plan."""
    items = [pr for pr in prs if isinstance(pr, dict)]
    by_number = {
        int(pr.get("number") or 0): pr
        for pr in items
        if int(pr.get("number") or 0) > 0
    }
    sources = sorted(
        items,
        key=lambda pr: (
            str(pr.get("created_at") or ""),
            int(pr.get("number") or 0),
        ),
        reverse=True,
    )

    claims: dict[int, Retirement] = {}
    for source in sources:
        if not _trusted_open_source(
            source,
            repo=repo,
            default_branch=default_branch,
            trusted_author=trusted_author,
        ):
            continue
        source_number = int(source.get("number") or 0)
        for target_number in superseded_numbers(source.get("body")):
            if target_number in claims:
                continue
            target = by_number.get(target_number)
            if target is None:
                continue
            allowed, _ = eligible_pair(
                source,
                target,
                repo=repo,
                default_branch=default_branch,
                trusted_author=trusted_author,
            )
            if not allowed:
                continue
            claims[target_number] = Retirement(
                source_number=source_number,
                target_number=target_number,
            )
            if len(claims) >= max_mutations:
                return list(claims.values())
    return list(claims.values())


def build_reverse_sync_plan(
    prs: Iterable[dict[str, Any]],
    *,
    repo: str,
    default_branch: str,
    trusted_author: str,
    max_mutations: int,
) -> list[ReverseSyncRetirement]:
    """Build a deterministic plan for exact automation reverse-sync PRs."""
    eligible: list[dict[str, Any]] = []
    for pr in prs:
        if not isinstance(pr, dict):
            continue
        allowed, _ = eligible_reverse_sync(
            pr,
            repo=repo,
            default_branch=default_branch,
            trusted_author=trusted_author,
        )
        if allowed:
            eligible.append(pr)

    eligible.sort(
        key=lambda pr: (
            str(pr.get("created_at") or ""),
            int(pr.get("number") or 0),
        )
    )
    return [
        ReverseSyncRetirement(number=int(pr["number"]))
        for pr in eligible[:max_mutations]
    ]


def fetch_pr(api: GitHubApi, repo: str, number: int) -> dict[str, Any]:
    status, payload, _ = _request_with_retry(api, f"/repos/{repo}/pulls/{number}")
    if status != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"failed to refresh PR #{number}: HTTP {status}")
    return payload


def close_pr(api: GitHubApi, repo: str, number: int) -> str:
    status, payload, _ = _request_with_retry(
        api,
        f"/repos/{repo}/pulls/{number}",
        method="PATCH",
        payload={"state": "closed"},
    )
    if status == 200 and isinstance(payload, dict):
        if str(payload.get("state") or "").lower() == "closed":
            return "closed"
        raise RuntimeError(f"PR #{number} close response did not confirm closed state")

    if status in {404, 409, 422}:
        refreshed = fetch_pr(api, repo, number)
        if str(refreshed.get("state") or "").lower() == "closed":
            return "already-closed"
    raise RuntimeError(f"failed to close PR #{number}: HTTP {status}")


def _bounded_mutation_limit(raw: object) -> int:
    try:
        value = int(str(raw))
    except (TypeError, ValueError):
        value = DEFAULT_MAX_MUTATIONS
    return max(1, min(value, ABSOLUTE_MAX_MUTATIONS))


def execute(
    api: GitHubApi,
    *,
    repo: str,
    default_branch: str,
    trusted_author: str,
    max_mutations: int,
) -> dict[str, int]:
    if not repo or "/" not in repo:
        raise RuntimeError("invalid repository identity")
    if not default_branch:
        raise RuntimeError("missing default branch")
    if not trusted_author:
        raise RuntimeError("missing trusted author")

    open_prs = list_open_prs(api, repo=repo, default_branch=default_branch)
    reverse_sync_plan = build_reverse_sync_plan(
        open_prs,
        repo=repo,
        default_branch=default_branch,
        trusted_author=trusted_author,
        max_mutations=max_mutations,
    )
    remaining = max(0, max_mutations - len(reverse_sync_plan))
    plan = build_retirement_plan(
        open_prs,
        repo=repo,
        default_branch=default_branch,
        trusted_author=trusted_author,
        max_mutations=remaining,
    ) if remaining else []

    totals = {
        "open_scanned": len(open_prs),
        "reverse_sync_planned": len(reverse_sync_plan),
        "reverse_sync_closed": 0,
        "reverse_sync_already_closed": 0,
        "reverse_sync_revalidation_skipped": 0,
        "planned": len(plan),
        "closed": 0,
        "already_closed": 0,
        "revalidation_skipped": 0,
    }

    for sync in reverse_sync_plan:
        fresh = fetch_pr(api, repo, sync.number)
        allowed, reason = eligible_reverse_sync(
            fresh,
            repo=repo,
            default_branch=default_branch,
            trusted_author=trusted_author,
        )
        if not allowed:
            totals["reverse_sync_revalidation_skipped"] += 1
            print(
                "skip reverse-sync retirement after revalidation: "
                f"pr=#{sync.number} reason={reason}"
            )
            continue

        outcome = close_pr(api, repo, sync.number)
        if outcome == "closed":
            totals["reverse_sync_closed"] += 1
        else:
            totals["reverse_sync_already_closed"] += 1
        print(f"retired reverse-sync PR: pr=#{sync.number} outcome={outcome}")

    for retirement in plan:
        # Re-read both PRs immediately before mutation. The current source must
        # still be open and must still explicitly supersede the current target.
        source = fetch_pr(api, repo, retirement.source_number)
        target = fetch_pr(api, repo, retirement.target_number)
        allowed, reason = eligible_pair(
            source,
            target,
            repo=repo,
            default_branch=default_branch,
            trusted_author=trusted_author,
        )
        if not allowed:
            totals["revalidation_skipped"] += 1
            print(
                "skip retirement after revalidation: "
                f"source=#{retirement.source_number} "
                f"target=#{retirement.target_number} reason={reason}"
            )
            continue

        outcome = close_pr(api, repo, retirement.target_number)
        if outcome == "closed":
            totals["closed"] += 1
        else:
            totals["already_closed"] += 1
        print(
            "retired superseded PR: "
            f"source=#{retirement.source_number} "
            f"target=#{retirement.target_number} outcome={outcome}"
        )

    return totals


def main() -> int:
    token = os.environ["GH_TOKEN"]
    repo = os.environ["REPO"]
    default_branch = os.environ["DEFAULT_BRANCH"]
    trusted_author = os.environ["TRUSTED_AUTHOR"]
    max_mutations = _bounded_mutation_limit(
        os.environ.get("MAX_MUTATIONS", DEFAULT_MAX_MUTATIONS)
    )

    api = GitHubApi(token)
    try:
        totals = execute(
            api,
            repo=repo,
            default_branch=default_branch,
            trusted_author=trusted_author,
            max_mutations=max_mutations,
        )
    except RuntimeError as exc:
        print(f"PR churn control failed: {exc}")
        return 1

    print(
        "PR churn control complete: "
        + " ".join(f"{key}={value}" for key, value in totals.items())
    )
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## PR churn control\n")
            handle.write(
                f"- Open PRs scanned: {totals['open_scanned']}\n"
            )
            handle.write(
                "- Exact reverse-sync PRs planned: "
                f"{totals['reverse_sync_planned']}\n"
            )
            handle.write(
                "- Exact reverse-sync PRs closed: "
                f"{totals['reverse_sync_closed']}\n"
            )
            handle.write(
                "- Reverse-sync revalidation skips: "
                f"{totals['reverse_sync_revalidation_skipped']}\n"
            )
            handle.write(f"- Explicit retirements planned: {totals['planned']}\n")
            handle.write(f"- PRs closed: {totals['closed']}\n")
            handle.write(
                f"- Already closed during mutation: {totals['already_closed']}\n"
            )
            handle.write(
                "- Revalidation skips: "
                f"{totals['revalidation_skipped']}\n"
            )
            handle.write(
                "- Policy: newer trusted default-base PRs may retire older PRs "
                "only through an explicit `Supersedes #…` directive. In addition, "
                "the exact owner-authored reverse-sync automation template may be "
                "retired when it uses the default branch as head and targets a "
                "non-protected branch. Drafts, foreign repositories/authors, "
                "protected bases, and preserve-labeled PRs are never retired.\n"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
