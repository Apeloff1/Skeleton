"""Bounded branch-backed dispatcher for the canonical auto-merge control plane."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

MAX_OUTPUT = 2_000_000
EXCLUDED_PREFIXES = ("backup/", "archive/", "archived/", "snapshot/", "snapshots/")
OPT_OUT_LABELS = frozenset({"do-not-merge", "automerge:off", "merge:manual"})
STATE_ORDER = {
    "clean": 0,
    "has_hooks": 1,
    "unstable": 2,
    "blocked": 3,
    "behind": 4,
    "dirty": 5,
    "unknown": 6,
}


class BranchMergeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Branch:
    name: str
    protected: bool = False


@dataclass(frozen=True, slots=True)
class PullRequest:
    number: int
    head: str
    base: str
    draft: bool
    labels: tuple[str, ...]
    state: str
    url: str = ""


@dataclass(frozen=True, slots=True)
class Candidate:
    number: int
    branch: str
    state: str
    url: str


@dataclass(frozen=True, slots=True)
class Plan:
    repository: str
    base: str
    observed_at: int
    inventory_complete: bool
    branch_count: int
    pr_count: int
    eligible_count: int
    draft_count: int
    opt_out_count: int
    ambiguous_count: int
    unpaired_count: int
    candidates: tuple[Candidate, ...]
    max_merges: int
    dispatch: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["candidates"] = [asdict(item) for item in self.candidates]
        return value


def _repo(value: str) -> str:
    value = value.strip()
    if value.count("/") != 1:
        raise BranchMergeError("repository must be owner/name")
    owner, name = value.split("/", 1)
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if not owner or not name or any(ch not in allowed for ch in owner + name):
        raise BranchMergeError("repository contains unsupported characters")
    return value


def _ref(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 240:
        raise BranchMergeError("invalid branch ref")
    if value.startswith(("-", "/")) or value.endswith("/"):
        raise BranchMergeError("unsafe branch ref")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise BranchMergeError("unsafe branch ref")
    if ".." in value or "//" in value or "@{" in value or "\\" in value:
        raise BranchMergeError("unsafe branch ref")
    return value


def _gh(args: Sequence[str], timeout: int = 30) -> str:
    try:
        proc = subprocess.run(
            ["gh", *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BranchMergeError("GitHub CLI invocation failed") from exc
    if proc.returncode != 0:
        detail = proc.stderr.strip().splitlines()
        tail = detail[-1][:240] if detail else "unknown GitHub error"
        raise BranchMergeError(f"GitHub CLI failed: {tail}")
    if len(proc.stdout.encode("utf-8")) > MAX_OUTPUT:
        raise BranchMergeError("GitHub output exceeded byte budget")
    return proc.stdout


def _json(args: Sequence[str]) -> object:
    raw = _gh(args)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BranchMergeError("GitHub returned invalid JSON") from exc


def _label_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out: list[str] = []
    for item in value:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str) and name.strip():
            out.append(name.strip().casefold())
    return tuple(dict.fromkeys(out))


def list_branches(repository: str, max_branches: int) -> tuple[tuple[Branch, ...], bool]:
    if max_branches < 1 or max_branches > 1000:
        raise BranchMergeError("max_branches out of range")
    rows: list[Branch] = []
    page = 1
    page_size = min(100, max_branches)
    complete = True
    while len(rows) < max_branches:
        value = _json(
            [
                "api",
                f"repos/{repository}/branches?per_page={page_size}&page={page}",
            ]
        )
        if not isinstance(value, list):
            raise BranchMergeError("branch inventory was not a list")
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                rows.append(Branch(_ref(item["name"]), bool(item.get("protected", False))))
                if len(rows) >= max_branches:
                    break
        if len(value) < page_size:
            break
        if len(rows) >= max_branches:
            complete = False
            break
        page += 1
    return tuple(rows), complete


def list_prs(
    repository: str,
    base: str,
    limit: int = 200,
) -> tuple[tuple[PullRequest, ...], bool]:
    if limit < 1 or limit > 500:
        raise BranchMergeError("PR inventory limit out of range")
    value = _json(
        [
            "pr",
            "list",
            "--repo",
            repository,
            "--state",
            "open",
            "--base",
            base,
            "--limit",
            str(limit),
            "--json",
            "number,headRefName,baseRefName,isDraft,labels,mergeStateStatus,url",
        ]
    )
    if not isinstance(value, list):
        raise BranchMergeError("PR inventory was not a list")
    rows: list[PullRequest] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        number = item.get("number")
        head = item.get("headRefName")
        target = item.get("baseRefName")
        if isinstance(number, bool) or not isinstance(number, int):
            continue
        if not isinstance(head, str) or not isinstance(target, str):
            continue
        state = str(item.get("mergeStateStatus", "unknown")).strip().casefold()
        if state not in STATE_ORDER:
            state = "unknown"
        rows.append(
            PullRequest(
                number=number,
                head=_ref(head),
                base=_ref(target),
                draft=bool(item.get("isDraft", False)),
                labels=_label_names(item.get("labels")),
                state=state,
                url=str(item.get("url", "")).strip(),
            )
        )
    return tuple(rows), len(value) < limit


def build_plan(
    repository: str,
    base: str,
    branches: Iterable[Branch],
    prs: Iterable[PullRequest],
    *,
    complete: bool,
    max_candidates: int = 40,
    max_merges: int = 3,
    observed_at: int | None = None,
) -> Plan:
    repository = _repo(repository)
    base = _ref(base)
    if max_candidates < 1 or max_candidates > 250:
        raise BranchMergeError("max_candidates out of range")
    if max_merges < 1 or max_merges > 20:
        raise BranchMergeError("max_merges out of range")

    branch_rows = tuple(branches)
    pr_rows = tuple(prs)
    branch_names = {
        row.name
        for row in branch_rows
        if not row.protected
        and row.name != base
        and not any(row.name.casefold().startswith(p) for p in EXCLUDED_PREFIXES)
    }

    by_head: dict[str, list[PullRequest]] = {}
    for pr in pr_rows:
        if pr.base == base and pr.head in branch_names:
            by_head.setdefault(pr.head, []).append(pr)

    drafts = 0
    opted_out = 0
    ambiguous = 0
    paired: set[str] = set()
    candidates: list[Candidate] = []
    for head in sorted(by_head):
        paired.add(head)
        matches = by_head[head]
        if len(matches) != 1:
            ambiguous += 1
            continue
        pr = matches[0]
        if pr.draft:
            drafts += 1
            continue
        if OPT_OUT_LABELS.intersection(pr.labels):
            opted_out += 1
            continue
        candidates.append(Candidate(pr.number, head, pr.state, pr.url))

    candidates.sort(key=lambda item: (STATE_ORDER.get(item.state, 99), item.number, item.branch))
    selected = tuple(candidates[:max_candidates])
    unpaired = sum(1 for name in branch_names if name not in paired)

    if not complete:
        dispatch = False
        reason = "repository-inventory-truncated"
    elif not selected:
        dispatch = False
        reason = "no-eligible-branch-backed-prs"
    else:
        dispatch = True
        reason = "eligible-branch-backed-prs"

    return Plan(
        repository=repository,
        base=base,
        observed_at=int(time.time()) if observed_at is None else observed_at,
        inventory_complete=complete,
        branch_count=len(branch_rows),
        pr_count=len(pr_rows),
        eligible_count=len(candidates),
        draft_count=drafts,
        opt_out_count=opted_out,
        ambiguous_count=ambiguous,
        unpaired_count=unpaired,
        candidates=selected,
        max_merges=min(max_merges, max(1, len(selected))),
        dispatch=dispatch,
        reason=reason,
    )


def dispatch(plan: Plan, mode: str = "direct") -> bool:
    if not plan.dispatch:
        return False
    if mode not in {"observe", "direct", "native"}:
        raise BranchMergeError("unsupported auto-merge mode")
    _gh(
        [
            "workflow",
            "run",
            "automerge-control-plane.yml",
            "--repo",
            plan.repository,
            "--ref",
            plan.base,
            "-f",
            f"mode={mode}",
            "-f",
            f"max_merges={plan.max_merges}",
        ]
    )
    return True


def _env_int(name: str, default: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise BranchMergeError(f"{name} must be an integer") from exc
    if value < 1 or value > maximum:
        raise BranchMergeError(f"{name} out of range")
    return value


def _env_bool(name: str) -> bool:
    raw = os.environ.get(name, "").strip().casefold()
    if raw in {"", "0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    raise BranchMergeError(f"{name} must be boolean")


def _write_report(path: str, plan: Plan, dispatched: bool, observe_only: bool) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {"plan": plan.as_dict(), "dispatched": dispatched, "observe_only": observe_only},
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _summary(plan: Plan, dispatched: bool) -> None:
    raw = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not raw:
        return
    path = Path(raw)
    if not path.is_absolute():
        return
    rows = [
        "# Branch merge manager",
        "",
        f"- Decision: {'DISPATCH' if dispatched else 'HOLD'}",
        f"- Reason: {plan.reason}",
        f"- Inventory complete: {plan.inventory_complete}",
        f"- Branches / PRs: {plan.branch_count} / {plan.pr_count}",
        f"- Eligible: {plan.eligible_count}",
        f"- Drafts held: {plan.draft_count}",
        f"- Opt-outs held: {plan.opt_out_count}",
        f"- Ambiguous heads held: {plan.ambiguous_count}",
        f"- Unpaired branches: {plan.unpaired_count}",
        f"- Merge budget: {plan.max_merges}",
        "",
        "## Candidates",
    ]
    rows.extend(
        f"- PR #{item.number}: {item.branch} ({item.state})"
        for item in plan.candidates
    )
    if not plan.candidates:
        rows.append("- none")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--base", default=os.environ.get("BRANCH_MERGE_DEFAULT_BRANCH", "main"))
    parser.add_argument("--report-json", default=".branch-merge/report.json")
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args(argv)

    repository = _repo(args.repo)
    base = _ref(args.base)
    max_branches = _env_int("BRANCH_MERGE_MAX_BRANCHES", 300, 1000)
    max_candidates = _env_int("BRANCH_MERGE_MAX_CANDIDATES", 40, 250)
    max_merges = _env_int("BRANCH_MERGE_MAX_MERGES", 3, 20)
    observe_only = args.observe_only or _env_bool("BRANCH_MERGE_OBSERVE_ONLY")

    branches, complete = list_branches(repository, max_branches)
    prs, pr_complete = list_prs(repository, base)
    complete = complete and pr_complete
    plan = build_plan(
        repository,
        base,
        branches,
        prs,
        complete=complete,
        max_candidates=max_candidates,
        max_merges=max_merges,
    )
    dispatched = False
    if plan.dispatch and not observe_only:
        dispatched = dispatch(plan)
    _write_report(args.report_json, plan, dispatched, observe_only)
    _summary(plan, dispatched)
    print(json.dumps({"dispatch": dispatched, "reason": plan.reason, "eligible": plan.eligible_count}, sort_keys=True))
    return 0


def main() -> int:
    try:
        return run()
    except BranchMergeError as exc:
        print(f"branch merge manager: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
