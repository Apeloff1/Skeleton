"""Command-line entry point for trusted default-branch auto-merge automation."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
from typing import Iterable, Sequence

from .automerge_engine import (
    EngineConfig,
    assert_report_consistent,
    reconcile,
    report_markdown,
)
from .automerge_github import AutoMergeGitHubError, GitHubAutoMergeClient
from .automerge_ledger import MergeLedger
from .automerge_model import (
    AutoMergePolicy,
    GateRequirement,
    MergeBudget,
    MergeMethod,
    MergeMode,
)


BASE_REQUIRED = (
    "CI/CD",
    "Merge Readiness",
    "Secret scanning",
    "Malware Gate",
    "Repository Hygiene Gate",
    "Artifact Policy",
    "Provenance Policy",
    "PR Hygiene",
)


def _csv(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return ()
    return tuple(
        dict.fromkeys(
            item.strip()
            for item in raw.split(",")
            if item.strip()
        )
    )


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value


def _mode(value: str) -> MergeMode:
    normalized = value.strip().casefold().replace("-", "_")
    aliases = {
        "observe": MergeMode.OBSERVE,
        "dry_run": MergeMode.OBSERVE,
        "native": MergeMode.ENABLE_NATIVE,
        "enable_native": MergeMode.ENABLE_NATIVE,
        "merge": MergeMode.MERGE_DIRECT,
        "direct": MergeMode.MERGE_DIRECT,
        "merge_direct": MergeMode.MERGE_DIRECT,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported auto-merge mode: {value!r}") from exc


def _method(value: str) -> MergeMethod:
    normalized = value.strip().casefold()
    try:
        return MergeMethod(normalized)
    except ValueError as exc:
        raise ValueError(f"unsupported merge method: {value!r}") from exc


def _required_workflows(extra: Iterable[str]) -> tuple[GateRequirement, ...]:
    names = tuple(dict.fromkeys([*BASE_REQUIRED, *extra]))
    return tuple(GateRequirement(name) for name in names)


def policy_from_env(
    *,
    repository: str,
    default_branch: str,
    mode: MergeMode | None = None,
    method: MergeMethod | None = None,
) -> AutoMergePolicy:
    owner = repository.split("/", 1)[0].casefold()
    extra_required = _csv(os.getenv("AUTOMERGE_REQUIRED_WORKFLOWS"))
    owners = _csv(os.getenv("AUTOMERGE_OWNER_LOGINS")) or (owner,)
    trusted_bots = _csv(os.getenv("AUTOMERGE_TRUSTED_BOTS")) or (
        "dependabot[bot]",
    )
    opt_in = _csv(os.getenv("AUTOMERGE_OPT_IN_LABELS")) or ("automerge",)
    opt_out = _csv(os.getenv("AUTOMERGE_OPT_OUT_LABELS")) or (
        "do-not-merge",
        "automerge:off",
    )

    budget = MergeBudget(
        max_merges=_env_int(
            "AUTOMERGE_MAX_MERGES",
            3,
            minimum=1,
            maximum=20,
        ),
        max_stack_merges=_env_int(
            "AUTOMERGE_MAX_STACK_MERGES",
            2,
            minimum=1,
            maximum=20,
        ),
        max_changed_files=_env_int(
            "AUTOMERGE_MAX_CHANGED_FILES",
            250,
            minimum=1,
            maximum=3000,
        ),
        max_line_delta=_env_int(
            "AUTOMERGE_MAX_LINE_DELTA",
            20_000,
            minimum=1,
            maximum=500_000,
        ),
        stability_seconds=_env_int(
            "AUTOMERGE_STABILITY_SECONDS",
            30,
            minimum=0,
            maximum=86_400,
        ),
        max_open_pr_scan=_env_int(
            "AUTOMERGE_MAX_OPEN_PR_SCAN",
            250,
            minimum=1,
            maximum=1000,
        ),
    )

    return AutoMergePolicy(
        default_branch=default_branch,
        mode=mode or _mode(os.getenv("AUTOMERGE_MODE", "merge_direct")),
        merge_method=method or _method(os.getenv("AUTOMERGE_MERGE_METHOD", "squash")),
        required_workflows=_required_workflows(extra_required),
        required_approvals=_env_int(
            "AUTOMERGE_REQUIRED_APPROVALS",
            0,
            minimum=0,
            maximum=10,
        ),
        require_resolved_threads=_env_bool(
            "AUTOMERGE_REQUIRE_RESOLVED_THREADS",
            True,
        ),
        require_no_changes_requested=_env_bool(
            "AUTOMERGE_REQUIRE_NO_CHANGES_REQUESTED",
            True,
        ),
        same_repository_only=_env_bool(
            "AUTOMERGE_SAME_REPOSITORY_ONLY",
            True,
        ),
        owner_logins=owners,
        trusted_bot_logins=trusted_bots,
        opt_in_labels=opt_in,
        opt_out_labels=opt_out,
        allow_owner_without_opt_in=_env_bool(
            "AUTOMERGE_ALLOW_OWNER_WITHOUT_OPT_IN",
            True,
        ),
        allow_dependabot_without_opt_in=_env_bool(
            "AUTOMERGE_ALLOW_DEPENDABOT_WITHOUT_OPT_IN",
            True,
        ),
        allow_stack_child_merge=_env_bool(
            "AUTOMERGE_ALLOW_STACK_CHILD_MERGE",
            True,
        ),
        budget=budget,
    )


def engine_config_from_env() -> EngineConfig:
    workflows = _csv(os.getenv("AUTOMERGE_POST_MERGE_WORKFLOWS")) or (
        "merge-readiness.yml",
        "queue-drain.yml",
    )
    return EngineConfig(
        dispatch_post_merge=_env_bool(
            "AUTOMERGE_DISPATCH_POST_MERGE",
            True,
        ),
        post_merge_workflows=workflows,
        stop_after_stack_mutation=_env_bool(
            "AUTOMERGE_STOP_AFTER_STACK_MUTATION",
            True,
        ),
        fail_on_graph_error=_env_bool(
            "AUTOMERGE_FAIL_ON_GRAPH_ERROR",
            True,
        ),
    )


def _write_json(path: str | Path, value: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _append_step_summary(text: str) -> None:
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(text)


def _token() -> str:
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GH_TOKEN or GITHUB_TOKEN is required")
    return token


def _repository(value: str | None) -> str:
    repo = (value or os.getenv("GITHUB_REPOSITORY") or "").strip()
    if repo.count("/") != 1:
        raise ValueError("repository must be owner/name")
    return repo


def _default_branch(value: str | None) -> str:
    branch = (
        value
        or os.getenv("AUTOMERGE_DEFAULT_BRANCH")
        or os.getenv("GITHUB_DEFAULT_BRANCH")
        or "main"
    ).strip()
    if not branch:
        raise ValueError("default branch is required")
    return branch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed exact-head auto-merge control plane"
    )
    parser.add_argument("--repo")
    parser.add_argument("--base")
    parser.add_argument(
        "--mode",
        choices=("observe", "native", "direct"),
    )
    parser.add_argument(
        "--merge-method",
        choices=("squash", "merge", "rebase"),
    )
    parser.add_argument(
        "--ledger",
        default=os.getenv(
            "AUTOMERGE_LEDGER_PATH",
            ".automerge/ledger.jsonl",
        ),
    )
    parser.add_argument(
        "--report-json",
        default=os.getenv(
            "AUTOMERGE_REPORT_PATH",
            ".automerge/report.json",
        ),
    )
    parser.add_argument(
        "--print-policy",
        action="store_true",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="load configuration and ledger without contacting GitHub",
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        repository = _repository(args.repo)
        default_branch = _default_branch(args.base)
        mode = _mode(args.mode) if args.mode else None
        method = _method(args.merge_method) if args.merge_method else None
        policy = policy_from_env(
            repository=repository,
            default_branch=default_branch,
            mode=mode,
            method=method,
        )
        config = engine_config_from_env()
        ledger = MergeLedger.read(args.ledger)

        if args.print_policy:
            print(
                json.dumps(
                    asdict(policy),
                    sort_keys=True,
                    indent=2,
                    default=str,
                )
            )

        if args.validate_only:
            ledger.verify()
            return 0

        client = GitHubAutoMergeClient(
            _token(),
            repository,
            retries=_env_int(
                "AUTOMERGE_HTTP_RETRIES",
                3,
                minimum=0,
                maximum=10,
            ),
            timeout=_env_int(
                "AUTOMERGE_HTTP_TIMEOUT",
                30,
                minimum=1,
                maximum=120,
            ),
            max_pages=_env_int(
                "AUTOMERGE_MAX_PAGES",
                10,
                minimum=1,
                maximum=100,
            ),
        )

        report = reconcile(
            client,
            policy,
            ledger=ledger,
            config=config,
        )
        assert_report_consistent(report)
        ledger.verify()
        ledger.write(args.ledger)
        _write_json(args.report_json, asdict(report))
        summary = report_markdown(report)
        _append_step_summary(summary)
        print(summary, end="")
        return 0

    except (ValueError, AutoMergeGitHubError) as exc:
        print(f"automerge error: {exc}", file=sys.stderr)
        return 2


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
