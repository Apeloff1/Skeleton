"""Run admission and pull-request target discovery for runner v2.

Target selection is a security boundary.  Workflow-run hints are advisory;
immutable commit identity plus same-repository branch identity remain the
authority.  This module also assigns deterministic priority bands so manual and
completion-driven work is handled before background sweeps without allowing one
busy branch to monopolize a run.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote, urlencode

from .event_firewall import admit_workflow_run, event_from_env
from .runner_contracts import (
    AdmissionDecision,
    AdmissionState,
    PriorityBand,
    RunIdentity,
    RunTrigger,
    RunnerPolicy,
    Target,
    TargetSet,
    valid_repository,
    valid_sha,
)
from .runner_transport import BudgetedGitHubTransport


class TargetingError(RuntimeError):
    pass


def parse_pr_hints(raw: str | None) -> tuple[int, ...]:
    text = (raw or "").strip()
    if not text or text in {"[]", "null"}:
        return ()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TargetingError("invalid workflow_run PR hint JSON") from exc
    if not isinstance(payload, list):
        raise TargetingError("workflow_run PR hints must be a JSON array")
    result: list[int] = []
    seen: set[int] = set()
    for item in payload:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise TargetingError(f"invalid workflow_run PR hint: {item!r}")
        if item not in seen:
            seen.add(item)
            result.append(item)
    if len(result) > 100:
        raise TargetingError("workflow_run PR hints exceeded 100 entries")
    return tuple(result)


def identity_from_env(
    env: Mapping[str, str],
    *,
    repository: str,
    explicit_pr: int | None = None,
    default_branch: str | None = None,
    pr_hints: Sequence[int] = (),
) -> RunIdentity:
    if not valid_repository(repository):
        raise TargetingError("repository must be owner/name")
    head_sha = (env.get("WORKFLOW_RUN_HEAD_SHA") or "").strip().casefold()
    head_ref = (env.get("WORKFLOW_RUN_HEAD_REF") or "").strip()
    workflow_name = (env.get("WORKFLOW_RUN_NAME") or "").strip() or None
    event_name = (env.get("GITHUB_EVENT_NAME") or "").strip() or None
    actor = (env.get("GITHUB_ACTOR") or "").strip() or None
    default = (
        (default_branch or "").strip()
        or (env.get("DEFAULT_BRANCH") or "").strip()
        or (env.get("GITHUB_REF_NAME") or "").strip()
        or "main"
    )
    delivery = (
        (env.get("GITHUB_RUN_ID") or "").strip()
        or (env.get("GITHUB_DELIVERY_ID") or "").strip()
        or "local:manual"
    )
    raw_run_id = (env.get("WORKFLOW_RUN_ID") or "").strip()
    workflow_run_id: int | None = None
    if raw_run_id:
        try:
            workflow_run_id = int(raw_run_id)
        except ValueError as exc:
            raise TargetingError("WORKFLOW_RUN_ID must be an integer") from exc

    if explicit_pr is not None:
        trigger = RunTrigger.EXPLICIT
    elif head_sha and head_ref:
        trigger = (
            RunTrigger.DEFAULT_BRANCH_COMPLETION
            if head_ref == default
            else RunTrigger.WORKFLOW_COMPLETION
        )
    elif event_name == "schedule":
        trigger = RunTrigger.SCHEDULED_SWEEP
    elif event_name == "workflow_dispatch":
        trigger = RunTrigger.MANUAL_SWEEP
    else:
        trigger = RunTrigger.RECOVERY

    return RunIdentity(
        repository=repository,
        delivery_id=delivery,
        trigger=trigger,
        workflow_name=workflow_name,
        workflow_run_id=workflow_run_id,
        head_sha=head_sha or None,
        head_ref=head_ref or None,
        default_branch=default,
        explicit_pr=explicit_pr,
        hinted_prs=tuple(pr_hints),
        actor=actor,
        event_name=event_name,
    )


def admission_for_identity(
    identity: RunIdentity,
    policy: RunnerPolicy,
    env: Mapping[str, str],
) -> AdmissionDecision:
    """Apply event-firewall semantics plus runner-specific authority rules."""
    reasons: list[str] = []
    mutation_authorized = policy.mode.value == "apply"

    if identity.trigger is RunTrigger.EXPLICIT:
        priority = PriorityBand.INTERACTIVE
    elif identity.trigger in {
        RunTrigger.WORKFLOW_COMPLETION,
        RunTrigger.DEFAULT_BRANCH_COMPLETION,
    }:
        priority = PriorityBand.COMPLETION
    elif identity.trigger is RunTrigger.RECOVERY:
        priority = PriorityBand.RECOVERY
    else:
        priority = PriorityBand.SWEEP

    if identity.head_sha and identity.head_ref:
        event = event_from_env(
            env,
            repository=identity.repository,
            head_sha=identity.head_sha,
            head_branch=identity.head_ref,
            pr_hints_json=json.dumps(identity.hinted_prs),
        )
        firewall = admit_workflow_run(event)
        if firewall.dropped:
            return AdmissionDecision(
                state=AdmissionState.DROP,
                reasons=(firewall.reason,) if firewall.reason else ("event_firewall_drop",),
                mutation_authorized=False,
                priority=priority,
                identity_fingerprint=identity.fingerprint(),
            )
        if not firewall.mutation_authorized:
            mutation_authorized = False
            reasons.append(firewall.reason or "event_observe_only")

    if identity.trigger is RunTrigger.SCHEDULED_SWEEP:
        # Scheduled sweeps can discover and publish status but are deliberately
        # observe-only unless explicitly enabled by a recovery configuration.
        allow = (env.get("PR_AUTOMATION_SCHEDULE_MUTATIONS") or "").casefold()
        if allow not in {"1", "true", "yes", "on"}:
            mutation_authorized = False
            reasons.append("scheduled_sweep_observe_only")

    if policy.mode.value != "apply":
        mutation_authorized = False
        reasons.append("runner_mode_observe")

    state = (
        AdmissionState.ADMIT
        if mutation_authorized
        else AdmissionState.OBSERVE_ONLY
    )
    return AdmissionDecision(
        state=state,
        reasons=tuple(dict.fromkeys(reasons)) or ("admitted",),
        mutation_authorized=mutation_authorized,
        priority=priority,
        identity_fingerprint=identity.fingerprint(),
    )


def _pr_number(item: Mapping[str, Any]) -> int:
    raw = item.get("number")
    if isinstance(raw, bool):
        return 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def _same_repo_head(
    pr: Mapping[str, Any],
    *,
    repository: str,
    head_ref: str,
) -> bool:
    head = pr.get("head")
    if not isinstance(head, Mapping):
        return False
    repo = head.get("repo")
    full_name = repo.get("full_name") if isinstance(repo, Mapping) else None
    return (
        isinstance(full_name, str)
        and full_name.casefold() == repository.casefold()
        and str(head.get("ref") or "") == head_ref
    )


def _allowed_base(
    pr: Mapping[str, Any],
    allowed_bases: Sequence[str],
) -> bool:
    base = pr.get("base")
    base_ref = (
        str(base.get("ref") or "")
        if isinstance(base, Mapping)
        else ""
    )
    allowed = {item.casefold() for item in allowed_bases}
    return base_ref.casefold() in allowed


def _head_sha(pr: Mapping[str, Any]) -> str | None:
    head = pr.get("head")
    raw = head.get("sha") if isinstance(head, Mapping) else None
    if not isinstance(raw, str):
        return None
    value = raw.casefold()
    return value if valid_sha(value) else None


def _target(
    number: int,
    *,
    reason: str,
    priority: PriorityBand,
    hinted: bool = False,
    by_sha: bool = False,
    by_branch: bool = False,
) -> Target:
    return Target(
        number=number,
        reason=reason,
        priority=priority,
        hinted=hinted,
        associated_by_sha=by_sha,
        associated_by_branch=by_branch,
    )


class TargetResolver:
    def __init__(
        self,
        transport: BudgetedGitHubTransport,
        policy: RunnerPolicy,
    ) -> None:
        self.transport = transport
        self.policy = policy

    def _fetch_pr(self, repository: str, number: int) -> Mapping[str, Any]:
        payload = self.transport.get(
            f"/repos/{repository}/pulls/{number}"
        )
        if not isinstance(payload, Mapping):
            raise TargetingError(f"PR #{number} response was not an object")
        return payload

    def _open_prs(
        self,
        repository: str,
    ) -> tuple[list[Mapping[str, Any]], bool]:
        # Scan a bounded repository window before applying the target cap.
        # Policy filtering happens after discovery, so disallowed base branches
        # cannot consume all target slots and starve eligible PRs later in the
        # same bounded inventory.
        return self.transport.paged_list(
            f"/repos/{repository}/pulls?state=open&sort=updated&direction=asc",
            max_pages=self.policy.limits.max_pages,
        )

    def _associated_by_sha(
        self,
        repository: str,
        sha: str,
    ) -> tuple[list[Mapping[str, Any]], bool]:
        quoted = quote(sha, safe="")
        return self.transport.paged_list(
            f"/repos/{repository}/commits/{quoted}/pulls"
        )

    def _branch_history(
        self,
        repository: str,
        head_ref: str,
    ) -> tuple[list[Mapping[str, Any]], bool]:
        owner = repository.split("/", 1)[0]
        query = urlencode(
            {
                "state": "all",
                "head": f"{owner}:{head_ref}",
                "sort": "updated",
                "direction": "desc",
            }
        )
        return self.transport.paged_list(
            f"/repos/{repository}/pulls?{query}"
        )

    def resolve(self, identity: RunIdentity) -> TargetSet:
        before = self.transport.request_count
        priority = {
            RunTrigger.EXPLICIT: PriorityBand.INTERACTIVE,
            RunTrigger.WORKFLOW_COMPLETION: PriorityBand.COMPLETION,
            RunTrigger.DEFAULT_BRANCH_COMPLETION: PriorityBand.COMPLETION,
            RunTrigger.RECOVERY: PriorityBand.RECOVERY,
            RunTrigger.SCHEDULED_SWEEP: PriorityBand.SWEEP,
            RunTrigger.MANUAL_SWEEP: PriorityBand.SWEEP,
        }[identity.trigger]

        if identity.explicit_pr is not None:
            # The explicit PR number is already validated by RunIdentity.
            # Do not prefetch it here: EvidenceCollector owns the authoritative
            # PR read and _process_target isolates collection failures into a
            # per-target FAILED result instead of crashing the whole runner.
            return TargetSet(
                repository=identity.repository,
                targets=(
                    _target(
                        identity.explicit_pr,
                        reason="explicit_pr",
                        priority=PriorityBand.INTERACTIVE,
                    ),
                ),
                complete=True,
                reason="explicit",
                requests_used=self.transport.request_count - before,
            )

        limit = self.policy.limits.max_targets
        if identity.trigger in {
            RunTrigger.SCHEDULED_SWEEP,
            RunTrigger.MANUAL_SWEEP,
            RunTrigger.RECOVERY,
            RunTrigger.DEFAULT_BRANCH_COMPLETION,
        }:
            items, inventory_complete = self._open_prs(
                identity.repository,
            )
            eligible = [
                item
                for item in items
                if _pr_number(item) > 0
                and _allowed_base(item, self.policy.core.allowed_bases)
            ]
            truncated = len(eligible) > limit
            targets = tuple(
                _target(
                    _pr_number(item),
                    reason=(
                        "default_branch_completion"
                        if identity.trigger is RunTrigger.DEFAULT_BRANCH_COMPLETION
                        else "repository_sweep"
                    ),
                    priority=priority,
                )
                for item in eligible[:limit]
            )
            return TargetSet(
                repository=identity.repository,
                targets=targets,
                complete=inventory_complete and not truncated,
                reason=identity.trigger.value,
                requests_used=self.transport.request_count - before,
            )

        if not identity.head_sha or not identity.head_ref:
            raise TargetingError(
                "workflow completion requires immutable head SHA and head ref"
            )

        ordered: dict[int, Target] = {}

        for hinted in identity.hinted_prs:
            pr = self._fetch_pr(identity.repository, hinted)
            if (
                _same_repo_head(
                    pr,
                    repository=identity.repository,
                    head_ref=identity.head_ref,
                )
                and _allowed_base(pr, self.policy.core.allowed_bases)
                and _head_sha(pr) == identity.head_sha
            ):
                ordered[hinted] = _target(
                    hinted,
                    reason="validated_workflow_hint",
                    priority=priority,
                    hinted=True,
                    by_sha=True,
                    by_branch=True,
                )

        associated, associated_complete = self._associated_by_sha(
            identity.repository,
            identity.head_sha,
        )
        if not associated_complete:
            raise TargetingError(
                "commit-to-PR association exceeded bounded pagination"
            )
        for pr in associated:
            number = _pr_number(pr)
            if (
                number > 0
                and _same_repo_head(
                    pr,
                    repository=identity.repository,
                    head_ref=identity.head_ref,
                )
                and _allowed_base(pr, self.policy.core.allowed_bases)
                and _head_sha(pr) == identity.head_sha
            ):
                prior = ordered.get(number)
                ordered[number] = _target(
                    number,
                    reason=(
                        prior.reason
                        if prior is not None
                        else "commit_sha_association"
                    ),
                    priority=priority,
                    hinted=prior.hinted if prior else False,
                    by_sha=True,
                    by_branch=True,
                )

        if not ordered:
            history, history_complete = self._branch_history(
                identity.repository,
                identity.head_ref,
            )
            if not history_complete:
                raise TargetingError(
                    "branch history exceeded bounded pagination"
                )
            for pr in history:
                number = _pr_number(pr)
                if (
                    number > 0
                    and _same_repo_head(
                        pr,
                        repository=identity.repository,
                        head_ref=identity.head_ref,
                    )
                    and _allowed_base(pr, self.policy.core.allowed_bases)
                    and _head_sha(pr) == identity.head_sha
                ):
                    ordered[number] = _target(
                        number,
                        reason="exact_branch_history_match",
                        priority=priority,
                        by_sha=True,
                        by_branch=True,
                    )

        targets = tuple(ordered[number] for number in sorted(ordered))
        if len(targets) > limit:
            targets = targets[:limit]
            complete = False
        else:
            complete = True
        return TargetSet(
            repository=identity.repository,
            targets=targets,
            complete=complete,
            reason="workflow_completion",
            requests_used=self.transport.request_count - before,
        )


def merge_hint_sets(
    *sets: Iterable[int],
) -> tuple[int, ...]:
    ordered: dict[int, None] = {}
    for values in sets:
        for value in values:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise TargetingError(f"invalid PR hint: {value!r}")
            ordered[value] = None
    if len(ordered) > 100:
        raise TargetingError("combined PR hints exceeded 100 entries")
    return tuple(ordered)


def target_numbers(targets: TargetSet) -> tuple[int, ...]:
    return tuple(target.number for target in targets.targets)


def assert_mutation_target_identity(
    target: Target,
    pr: Mapping[str, Any],
    identity: RunIdentity,
    policy: RunnerPolicy,
) -> None:
    """Validate a target again before any mutation-capable collection."""
    number = _pr_number(pr)
    if number != target.number:
        raise TargetingError("target PR number changed")
    if identity.head_ref and identity.trigger is RunTrigger.WORKFLOW_COMPLETION:
        if not _same_repo_head(
            pr,
            repository=identity.repository,
            head_ref=identity.head_ref,
        ):
            raise TargetingError("workflow target branch identity changed")
    if not _allowed_base(pr, policy.core.allowed_bases):
        raise TargetingError("target base branch is outside policy")
    if identity.head_sha and identity.trigger is RunTrigger.WORKFLOW_COMPLETION:
        if _head_sha(pr) != identity.head_sha:
            raise TargetingError("workflow target head SHA changed")


__all__ = [
    "TargetResolver",
    "TargetingError",
    "admission_for_identity",
    "assert_mutation_target_identity",
    "identity_from_env",
    "merge_hint_sets",
    "parse_pr_hints",
    "target_numbers",
]
