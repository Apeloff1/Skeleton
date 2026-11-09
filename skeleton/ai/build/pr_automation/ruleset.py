"""Dry-run-first bootstrap for the repository PR safety ruleset.

The normal workflow token cannot administer repository rulesets. Owners can run
this module locally with an admin-capable token after reviewing the generated
payload. Dry-run is the default; mutation requires ``--apply`` explicitly.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .runner import GATE_CONTEXT


API = "https://api.github.com"
DEFAULT_GITHUB_ACTIONS_APP_ID = 15368
DEFAULT_MERGE_READINESS_CONTEXT = "Merge Readiness"


def build_ruleset(
    *,
    branch: str = "main",
    name: str = "PR automation merge safety",
    approvals: int = 1,
    gate_context: str = GATE_CONTEXT,
    merge_readiness_context: str = DEFAULT_MERGE_READINESS_CONTEXT,
    integration_id: int | None = DEFAULT_GITHUB_ACTIONS_APP_ID,
) -> dict[str, Any]:
    """Return a conservative repository-ruleset payload.

    The native aggregate CI context and the trusted automation gate are both
    required. Requiring the native context closes the window where a previously
    successful automation status could otherwise outlive a newly requested CI
    rerun; requiring the automation gate adds policy checks GitHub's native CI
    context does not encode (scope, fork policy, trust-surface quarantine, etc.).
    """

    if not branch or branch.startswith("refs/"):
        raise ValueError("branch must be a short branch name such as 'main'")
    if not name.strip():
        raise ValueError("ruleset name must not be empty")
    if not 0 <= approvals <= 10:
        raise ValueError("approvals must be between 0 and 10")
    if not gate_context.strip():
        raise ValueError("gate context must not be empty")
    if not merge_readiness_context.strip():
        raise ValueError("merge readiness context must not be empty")
    if gate_context == merge_readiness_context:
        raise ValueError("gate and merge readiness contexts must be distinct")
    if integration_id is not None and integration_id <= 0:
        raise ValueError("integration_id must be positive when supplied")

    required_checks: list[dict[str, Any]] = []
    for context in (merge_readiness_context, gate_context):
        check: dict[str, Any] = {"context": context}
        if integration_id is not None:
            check["integration_id"] = integration_id
        required_checks.append(check)

    return {
        "name": name.strip(),
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {
                "include": [f"refs/heads/{branch}"],
                "exclude": [],
            }
        },
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "pull_request",
                "parameters": {
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": False,
                    "require_last_push_approval": True,
                    "required_approving_review_count": approvals,
                    "required_review_thread_resolution": True,
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "do_not_enforce_on_create": False,
                    "required_status_checks": required_checks,
                },
            },
        ],
    }


def _request(token: str, method: str, url: str, body: dict[str, Any] | None = None) -> Any:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "skeleton-pr-ruleset-bootstrap/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=payload, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"GitHub HTTP {exc.code}: {detail}") from exc


def _find_ruleset(token: str, repository: str, name: str) -> int | None:
    owner, repo = repository.split("/", 1)
    rulesets = _request(token, "GET", f"{API}/repos/{owner}/{repo}/rulesets")
    if not isinstance(rulesets, list):
        raise RuntimeError("unexpected ruleset list response")
    matches = [item for item in rulesets if str(item.get("name") or "") == name]
    if len(matches) > 1:
        raise RuntimeError(f"multiple rulesets named {name!r}; refusing ambiguous update")
    if not matches:
        return None
    return int(matches[0]["id"])


def apply_ruleset(token: str, repository: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Create or replace the named repository ruleset idempotently."""

    if repository.count("/") != 1:
        raise ValueError("repository must be owner/name")
    owner, repo = repository.split("/", 1)
    ruleset_id = _find_ruleset(token, repository, str(payload["name"]))
    if ruleset_id is None:
        result = _request(token, "POST", f"{API}/repos/{owner}/{repo}/rulesets", payload)
    else:
        result = _request(token, "PUT", f"{API}/repos/{owner}/{repo}/rulesets/{ruleset_id}", payload)
    if not isinstance(result, dict):
        raise RuntimeError("unexpected ruleset mutation response")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or apply the PR automation repository ruleset.")
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY"))
    parser.add_argument("--branch", default="main")
    parser.add_argument("--name", default="PR automation merge safety")
    parser.add_argument("--approvals", type=int, default=1)
    parser.add_argument("--gate-context", default=GATE_CONTEXT)
    parser.add_argument("--merge-readiness-context", default=DEFAULT_MERGE_READINESS_CONTEXT)
    parser.add_argument("--integration-id", type=int, default=DEFAULT_GITHUB_ACTIONS_APP_ID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    if not args.repo or args.repo.count("/") != 1:
        parser.error("--repo or GITHUB_REPOSITORY must be owner/name")

    payload = build_ruleset(
        branch=args.branch,
        name=args.name,
        approvals=args.approvals,
        gate_context=args.gate_context,
        merge_readiness_context=args.merge_readiness_context,
        integration_id=args.integration_id,
    )
    if not args.apply:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        parser.error("--apply requires GH_TOKEN or GITHUB_TOKEN with repository administration write access")
    result = apply_ruleset(token, args.repo, payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
