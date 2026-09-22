"""CLI and environment configuration for PR automation runner v2.

The command line intentionally accepts the same target-selection arguments as
the legacy runner so the trusted workflow can switch engines without changing
its event identity protocol.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import sys
from typing import Mapping, Sequence

from .core import Mode, Policy
from .index import EventIndex
from .runner_contracts import RunnerLimits, RunnerPolicy
from .runner_engine import run_engine
from .runner_report import (
    append_step_summary,
    checkpoint_from_report,
    compact_report,
    markdown_summary,
    report_exit_code,
    save_checkpoint,
    write_report_json,
    write_transport_json,
)
from .runner_targeting import (
    admission_for_identity,
    identity_from_env,
    merge_hint_sets,
    parse_pr_hints,
)
from .runner_transport import BudgetedGitHubTransport
from .safety import load_operator_safety


def env_bool(
    env: Mapping[str, str],
    name: str,
    default: bool,
) -> bool:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    value = raw.casefold().strip()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def env_int(
    env: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = env.get(name)
    if raw is None or raw == "":
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


def csv(
    raw: str | None,
    *,
    casefold: bool = False,
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for part in (raw or "").split(","):
        value = part.strip()
        if not value:
            continue
        if casefold:
            value = value.casefold()
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def core_policy_from_env(env: Mapping[str, str]) -> Policy:
    allowed = csv(
        env.get("PR_AUTOMATION_ALLOWED_BASES", "main")
    )
    if not allowed:
        raise ValueError(
            "PR_AUTOMATION_ALLOWED_BASES must contain at least one branch"
        )
    return Policy(
        allowed_bases=allowed,
        required_approvals=env_int(
            env,
            "PR_AUTOMATION_REQUIRED_APPROVALS",
            0,
            minimum=0,
            maximum=50,
        ),
        require_no_changes_requested=env_bool(
            env,
            "PR_AUTOMATION_REQUIRE_NO_CHANGES_REQUESTED",
            True,
        ),
        require_resolved_threads=env_bool(
            env,
            "PR_AUTOMATION_REQUIRE_RESOLVED_THREADS",
            True,
        ),
        require_checks=env_bool(
            env,
            "PR_AUTOMATION_REQUIRE_CHECKS",
            True,
        ),
        allow_fork_merge=env_bool(
            env,
            "PR_AUTOMATION_ALLOW_FORK_MERGE",
            False,
        ),
        max_changed_files=env_int(
            env,
            "PR_AUTOMATION_MAX_CHANGED_FILES",
            250,
            minimum=1,
            maximum=3000,
        ),
        max_total_line_delta=env_int(
            env,
            "PR_AUTOMATION_MAX_LINE_DELTA",
            20_000,
            minimum=1,
            maximum=10_000_000,
        ),
        merge_when_ready=env_bool(
            env,
            "PR_AUTOMATION_MERGE_WHEN_READY",
            False,
        ),
    )


def limits_from_env(env: Mapping[str, str]) -> RunnerLimits:
    return RunnerLimits(
        max_targets=env_int(
            env,
            "PR_RUNNER_MAX_TARGETS",
            250,
            minimum=1,
            maximum=1000,
        ),
        max_requests=env_int(
            env,
            "PR_RUNNER_MAX_REQUESTS",
            2000,
            minimum=10,
            maximum=20_000,
        ),
        max_graphql_requests=env_int(
            env,
            "PR_RUNNER_MAX_GRAPHQL_REQUESTS",
            200,
            minimum=1,
            maximum=2000,
        ),
        max_mutations=env_int(
            env,
            "PR_AUTOMATION_MAX_MUTATIONS",
            1,
            minimum=0,
            maximum=20,
        ),
        max_pages=env_int(
            env,
            "PR_RUNNER_MAX_PAGES",
            20,
            minimum=1,
            maximum=100,
        ),
        max_response_bytes=env_int(
            env,
            "PR_RUNNER_MAX_RESPONSE_BYTES",
            8 * 1024 * 1024,
            minimum=1024,
            maximum=64 * 1024 * 1024,
        ),
        max_changed_files=env_int(
            env,
            "PR_AUTOMATION_MAX_CHANGED_FILES",
            250,
            minimum=1,
            maximum=3000,
        ),
        max_events_exported=env_int(
            env,
            "PR_RUNNER_MAX_EVENTS_EXPORTED",
            100_000,
            minimum=1,
            maximum=1_000_000,
        ),
        deadline_seconds=env_int(
            env,
            "PR_RUNNER_DEADLINE_SECONDS",
            600,
            minimum=30,
            maximum=3600,
        ),
        per_target_request_budget=env_int(
            env,
            "PR_RUNNER_PER_TARGET_REQUEST_BUDGET",
            100,
            minimum=10,
            maximum=1000,
        ),
        queue_pressure_threshold=env_int(
            env,
            "PR_AUTOMATION_MAX_QUEUED_ACTIONS_RUNS",
            40,
            minimum=0,
            maximum=100_000,
        ),
        minimum_rate_remaining=env_int(
            env,
            "PR_RUNNER_MIN_RATE_REMAINING",
            50,
            minimum=1,
            maximum=5000,
        ),
        retry_attempts=env_int(
            env,
            "PR_RUNNER_RETRY_ATTEMPTS",
            3,
            minimum=0,
            maximum=10,
        ),
        retry_ceiling_seconds=env_int(
            env,
            "PR_RUNNER_RETRY_CEILING_SECONDS",
            30,
            minimum=1,
            maximum=120,
        ),
    )


def runner_policy_from_env(
    env: Mapping[str, str],
) -> RunnerPolicy:
    mode_text = env.get("PR_AUTOMATION_MODE", "observe").casefold()
    try:
        mode = Mode(mode_text)
    except ValueError as exc:
        raise ValueError(
            "PR_AUTOMATION_MODE must be observe or apply"
        ) from exc
    merge_method = env.get(
        "PR_AUTOMATION_MERGE_METHOD",
        "squash",
    ).casefold()
    checks = csv(env.get("PR_AUTOMATION_REQUIRED_CHECKS", ""))
    if "PR Automation Gate" in checks:
        raise ValueError("PR Automation Gate cannot require itself")

    core = core_policy_from_env(env)
    if (
        mode is Mode.APPLY
        and core.merge_when_ready
        and (not core.require_checks or not checks)
    ):
        raise ValueError(
            "apply+merge requires checks and explicit "
            "PR_AUTOMATION_REQUIRED_CHECKS"
        )

    return RunnerPolicy(
        core=core,
        mode=mode,
        required_checks=checks,
        merge_method=merge_method,
        allowed_authors=csv(
            env.get("PR_RUNNER_ALLOWED_AUTHORS", ""),
            casefold=True,
        ),
        denied_labels=csv(
            env.get(
                "PR_RUNNER_DENIED_LABELS",
                "do-not-merge,automerge:off",
            ),
            casefold=True,
        ),
        required_labels=csv(
            env.get("PR_RUNNER_REQUIRED_LABELS", ""),
            casefold=True,
        ),
        protected_base_required=env_bool(
            env,
            "PR_RUNNER_REQUIRE_PROTECTED_BASE",
            True,
        ),
        exact_base_head_required=env_bool(
            env,
            "PR_RUNNER_REQUIRE_EXACT_BASE_HEAD",
            True,
        ),
        queue_pressure_hold=env_bool(
            env,
            "PR_RUNNER_QUEUE_PRESSURE_HOLD",
            True,
        ),
        publish_gate_status=env_bool(
            env,
            "PR_RUNNER_PUBLISH_GATE_STATUS",
            True,
        ),
        require_same_repository_head=env_bool(
            env,
            "PR_RUNNER_REQUIRE_SAME_REPOSITORY_HEAD",
            True,
        ),
        require_latest_reviews_on_head=env_bool(
            env,
            "PR_RUNNER_REQUIRE_LATEST_REVIEWS_ON_HEAD",
            True,
        ),
        limits=limits_from_env(env),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate and safely automate pull requests with runner v2."
    )
    parser.add_argument(
        "--repo",
        default=os.getenv("GITHUB_REPOSITORY"),
    )
    parser.add_argument("--pr", type=int)
    parser.add_argument(
        "--pr-hint",
        dest="pr_hints",
        type=int,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--pr-hints-json",
        default=os.getenv("WORKFLOW_RUN_PR_HINTS", ""),
    )
    parser.add_argument(
        "--head-sha",
        default=os.getenv("WORKFLOW_RUN_HEAD_SHA", ""),
    )
    parser.add_argument(
        "--head-ref",
        default=os.getenv("WORKFLOW_RUN_HEAD_REF", ""),
    )
    parser.add_argument(
        "--default-branch",
        default=(
            os.getenv("DEFAULT_BRANCH", "")
            or os.getenv("GITHUB_REF_NAME", "")
            or "main"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="maximum sweep targets; additionally bounded by PR_RUNNER_MAX_TARGETS",
    )
    parser.add_argument(
        "--index",
        default=os.getenv(
            "PR_AUTOMATION_INDEX",
            ".pr-automation/index.sqlite3",
        ),
    )
    parser.add_argument(
        "--export",
        default=os.getenv(
            "PR_AUTOMATION_EXPORT",
            ".pr-automation/index.jsonl",
        ),
    )
    parser.add_argument(
        "--report",
        default=os.getenv(
            "PR_RUNNER_REPORT",
            ".pr-automation/runner-report.json",
        ),
    )
    parser.add_argument(
        "--transport-report",
        default=os.getenv(
            "PR_RUNNER_TRANSPORT_REPORT",
            ".pr-automation/runner-transport.json",
        ),
    )
    parser.add_argument(
        "--checkpoint",
        default=os.getenv(
            "PR_RUNNER_CHECKPOINT",
            ".pr-automation/runner-checkpoint.json",
        ),
    )
    parser.add_argument(
        "--print-policy",
        action="store_true",
    )
    return parser


def _token(env: Mapping[str, str]) -> str:
    token = env.get("GITHUB_TOKEN", "") or env.get("GH_TOKEN", "")
    if not token:
        raise ValueError("GITHUB_TOKEN or GH_TOKEN is required")
    return token


def run_v2(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    source_env = dict(os.environ if env is None else env)

    if not args.repo or str(args.repo).count("/") != 1:
        parser.error("--repo or GITHUB_REPOSITORY must be owner/name")
    if args.pr is not None and args.pr <= 0:
        parser.error("--pr must be positive")
    if any(value <= 0 for value in args.pr_hints):
        parser.error("--pr-hint must be positive")
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")

    try:
        safety = load_operator_safety(source_env)
        if safety.blocked:
            print(
                json.dumps(
                    {
                        "kind": "pr-automation-operator-hold",
                        **safety.public_payload(),
                    },
                    sort_keys=True,
                )
            )
            return 0

        json_hints = parse_pr_hints(str(args.pr_hints_json or ""))
        hints = merge_hint_sets(json_hints, args.pr_hints)
        policy = runner_policy_from_env(source_env)

        # Keep the existing workflow's explicit --limit meaningful without
        # allowing it to raise the configured hard target cap.
        if args.limit < policy.limits.max_targets:
            limits = policy.limits
            from dataclasses import replace

            policy = replace(
                policy,
                limits=replace(
                    limits,
                    max_targets=args.limit,
                ),
            )

        env_for_identity = dict(source_env)
        env_for_identity["WORKFLOW_RUN_HEAD_SHA"] = str(
            args.head_sha or ""
        )
        env_for_identity["WORKFLOW_RUN_HEAD_REF"] = str(
            args.head_ref or ""
        )
        identity = identity_from_env(
            env_for_identity,
            repository=str(args.repo),
            explicit_pr=args.pr,
            default_branch=str(args.default_branch or "main"),
            pr_hints=hints,
        )
        admission = admission_for_identity(
            identity,
            policy,
            source_env,
        )

        if args.print_policy:
            print(
                json.dumps(
                    asdict(policy),
                    sort_keys=True,
                    indent=2,
                    default=str,
                )
            )

        transport = BudgetedGitHubTransport(
            _token(source_env),
            policy.limits,
            timeout_seconds=env_int(
                source_env,
                "PR_RUNNER_HTTP_TIMEOUT_SECONDS",
                30,
                minimum=1,
                maximum=120,
            ),
        )
        index = EventIndex(args.index)
        report = run_engine(
            transport=transport,
            index=index,
            policy=policy,
            identity=identity,
            admission=admission,
        )

        index.export_jsonl(args.export)
        write_report_json(args.report, report)
        write_transport_json(
            args.transport_report,
            report.transport,
        )
        save_checkpoint(
            args.checkpoint,
            checkpoint_from_report(report),
        )
        summary = markdown_summary(report)
        append_step_summary(summary, source_env)
        print(json.dumps(compact_report(report), sort_keys=True))
        return report_exit_code(report)
    except (ValueError, RuntimeError) as exc:
        print(
            f"runner v2 error: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    return run_v2(argv)


if __name__ == "__main__":
    raise SystemExit(main())
