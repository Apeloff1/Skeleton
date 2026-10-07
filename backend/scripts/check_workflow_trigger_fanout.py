"""Fail-closed GitHub Actions trigger-fanout audit.

Inspects ``.github/workflows`` event combinations and names avoidable run
classes without recommending removal of fork-PR, default-branch, schedule, or
security-scan coverage. Uses only the Python standard library so it can run
before project dependencies are installed. Opaque YAML is a hard failure;
the checker never guesses at aliases, tags, or merge keys.

This module is intentionally separate from the concurrency-key collision
audit: unique path ``check_workflow_trigger_fanout.py``, unique finding
prefixes ``trigger-fanout``, and unique run-class identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

FANOUT_ON_KEY_RE = re.compile(r"^(?:on|'on'|\"on\")\s*:\s*(?P<value>.*)$")
FANOUT_CHILD_KEY_RE = re.compile(
    r"^(?P<indent> +)(?:- )?(?P<key>['\"]?[A-Za-z][A-Za-z0-9_-]*['\"]?)\s*(?::(?P<rest>.*))?$"
)
FANOUT_SEQUENCE_ITEM_RE = re.compile(
    r"^(?P<indent> +)-\s+(?P<value>.*)$"
)
FANOUT_EVENT_NAME_EQ_RE = re.compile(
    r"github\.event_name\s*==\s*['\"](?P<event>[A-Za-z][A-Za-z0-9_]*)['\"]"
)
IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
FILTER_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
ALIAS_OR_ANCHOR_RE = re.compile(r"(?:^|[\s,{[])[*&][A-Za-z_]")
YAML_TAG_RE = re.compile(r"(?:^|[\s,{[])!!")
MERGE_KEY_RE = re.compile(r"(?:^|[\s,{[])<<\s*:")

MANUAL_EVENTS = frozenset({"workflow_dispatch", "workflow_call", "repository_dispatch"})
PERIODIC_EVENTS = frozenset({"schedule"})
REVIEW_EVENTS = frozenset(
    {"pull_request_review", "pull_request_review_comment"}
)
SKIP_NESTED_FILTER_KEYS = frozenset({"inputs", "outputs", "secrets"})
KNOWN_FILTER_KEYS = frozenset(
    {
        "types",
        "branches",
        "branches-ignore",
        "tags",
        "tags-ignore",
        "paths",
        "paths-ignore",
        "workflows",
        "inputs",
        "outputs",
        "secrets",
        "cron",
    }
)
PROTECTED_BRANCHES = frozenset({"main", "master", "develop", "dev"})
NOISY_PR_TYPES = frozenset(
    {
        "edited",
        "labeled",
        "unlabeled",
        "assigned",
        "unassigned",
        "milestoned",
        "demilestoned",
        "review_requested",
        "review_request_removed",
        "locked",
        "unlocked",
        "auto_merge_enabled",
        "auto_merge_disabled",
        "enqueued",
        "dequeued",
    }
)
SECURITY_COVERAGE_MARKERS = (
    "secret",
    "malware",
    "gitleaks",
    "security",
    "hygiene",
    "permission",
    "allowlist",
    "dependency-review",
    "provenance",
    "sast",
    "ioc",
    "codeql",
)
DISPATCHER_WORKFLOWS = frozenset({"repo-attention.yml", "repo-attention.yaml"})
ALL_BRANCH_GLOBS = frozenset({"*", "**", "**/**", "**/*", "*/*", "*/**"})
TYPICAL_PR_HEADS = ("cursor/example-feature", "hotfix-example")


@dataclass(frozen=True)
class TriggerEvent:
    name: str
    types: tuple[str, ...] | None = None
    branches: tuple[str, ...] | None = None
    branches_ignore: tuple[str, ...] | None = None
    paths: tuple[str, ...] | None = None
    paths_ignore: tuple[str, ...] | None = None
    tags: tuple[str, ...] | None = None
    tags_ignore: tuple[str, ...] | None = None
    workflows: tuple[str, ...] | None = None
    crons: tuple[str, ...] | None = None


@dataclass(frozen=True)
class TriggerFanoutRecord:
    workflow: str
    events: tuple[TriggerEvent, ...]
    routed_event_names: tuple[str, ...]
    security_coverage: bool
    dispatcher: bool


@dataclass(frozen=True)
class FanoutFinding:
    workflow: str
    kind: str
    run_class: str
    message: str

    def render(self) -> str:
        return (
            f"trigger-fanout {self.kind} {self.run_class}: "
            f"{self.workflow}: {self.message}"
        )


@dataclass(frozen=True)
class FanoutAudit:
    records: tuple[TriggerFanoutRecord, ...]
    findings: tuple[FanoutFinding, ...]

    def violations(self) -> list[str]:
        return [
            finding.render()
            for finding in self.findings
            if finding.kind in {"opaque", "avoidable"}
        ]

    def estimated_avoidable_run_classes(self) -> list[FanoutFinding]:
        return [
            finding
            for finding in self.findings
            if finding.kind in {"avoidable", "estimated"}
        ]


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _strip_comment(value: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(value):
        if in_single:
            if char == "'":
                in_single = False
            continue
        if in_double:
            if char == "\\":
                continue
            if char == '"':
                in_double = False
            continue
        if char == "'":
            in_single = True
            continue
        if char == '"':
            in_double = True
            continue
        if char == "#":
            return value[:index].rstrip()
    return value.strip()


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _yaml_key(entry: str) -> str:
    key = entry.partition(":")[0].strip()
    return _unquote(key)


def _is_opaque_fragment(value: str) -> bool:
    compact = value.strip()
    if not compact:
        return False
    if MERGE_KEY_RE.search(compact) or YAML_TAG_RE.search(compact):
        return True
    if ALIAS_OR_ANCHOR_RE.search(compact):
        return True
    return False


def _split_flow(value: str, opener: str, closer: str) -> list[str] | None:
    if not (value.startswith(opener) and value.endswith(closer)):
        return None
    items: list[str] = []
    token: list[str] = []
    depth = 0
    in_single = False
    in_double = False
    escaped = False
    for char in value[1:-1]:
        if in_single:
            token.append(char)
            if char == "'":
                in_single = False
            continue
        if in_double:
            token.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_double = False
            continue
        if char == "'":
            in_single = True
            token.append(char)
            continue
        if char == '"':
            in_double = True
            token.append(char)
            continue
        if char in "{[":
            depth += 1
            token.append(char)
            continue
        if char in "}]":
            depth -= 1
            token.append(char)
            continue
        if char == "," and depth == 0:
            entry = "".join(token).strip()
            if entry:
                items.append(entry)
            token = []
            continue
        token.append(char)
    if in_single or in_double or depth != 0:
        return None
    entry = "".join(token).strip()
    if entry:
        items.append(entry)
    return items


def _flow_sequence(value: str) -> list[str] | None:
    items = _split_flow(value, "[", "]")
    if items is None:
        return None
    parsed: list[str] = []
    for item in items:
        if _is_opaque_fragment(item) or item.startswith("{") or item.startswith("["):
            return None
        parsed.append(_unquote(item.strip()))
    return parsed


def _flow_mapping(value: str) -> list[tuple[str, str]] | None:
    items = _split_flow(value, "{", "}")
    if items is None:
        return None
    parsed: list[tuple[str, str]] = []
    for item in items:
        if _is_opaque_fragment(item) or ":" not in item:
            return None
        key, _, rest = item.partition(":")
        name = _unquote(key.strip())
        if not IDENTIFIER_RE.fullmatch(name.replace("-", "_")) and not FILTER_KEY_RE.fullmatch(name):
            return None
        parsed.append((name, rest.strip()))
    return parsed


def _top_level_matches(lines: list[str], pattern: re.Pattern[str]) -> list[tuple[int, re.Match[str]]]:
    matches: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match is not None and _indent(line) == 0:
            matches.append((index, match))
    return matches


def _block_children(lines: list[str], start: int) -> list[str]:
    children: list[str] = []
    cursor = start + 1
    while cursor < len(lines):
        line = lines[cursor]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            children.append(line)
            cursor += 1
            continue
        if _indent(line) == 0:
            break
        children.append(line)
        cursor += 1
    return children


def _direct_children(lines: list[str]) -> list[tuple[int, str]] | None:
    concrete = [
        (offset, line)
        for offset, line in enumerate(lines)
        if line.strip() and not line.strip().startswith("#")
    ]
    if not concrete:
        return []
    direct = min(_indent(line) for _offset, line in concrete)
    if direct == 0:
        return None
    selected: list[tuple[int, str]] = []
    for offset, line in concrete:
        width = _indent(line)
        if width < direct:
            return None
        if width == direct:
            selected.append((offset, line))
    return selected


def _nested_block(lines: list[str], start: int, parent_indent: int) -> list[str]:
    nested: list[str] = []
    cursor = start + 1
    while cursor < len(lines):
        line = lines[cursor]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            nested.append(line)
            cursor += 1
            continue
        if _indent(line) <= parent_indent:
            break
        nested.append(line)
        cursor += 1
    return nested


def _parse_string_list(inline: str, child_lines: list[str], label: str) -> tuple[tuple[str, ...] | None, str | None]:
    value = _strip_comment(inline)
    if value:
        if _is_opaque_fragment(value):
            return None, f"opaque {label} list"
        sequence = _flow_sequence(value)
        if sequence is None:
            return None, f"opaque {label} list"
        return tuple(sequence), None

    items: list[str] = []
    for line in child_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = FANOUT_SEQUENCE_ITEM_RE.match(line)
        if match is None:
            return None, f"opaque {label} list"
        item = _strip_comment(match.group("value"))
        if not item or item.endswith(":") or _is_opaque_fragment(item):
            if item.startswith("cron:"):
                cron_value = _strip_comment(item.partition(":")[2].strip())
                if not cron_value or _is_opaque_fragment(cron_value):
                    return None, f"opaque {label} list"
                items.append(_unquote(cron_value))
                continue
            return None, f"opaque {label} list"
        items.append(_unquote(item))
    if not items:
        return None, f"empty {label} list"
    return tuple(items), None


def _is_glob(value: str) -> bool:
    return any(char in value for char in "*?[")


def _github_glob_match(pattern: str, value: str) -> bool:
    """Match GitHub branch filters: ``*`` excludes ``/`` and ``**`` matches anything."""
    regex = "^"
    index = 0
    while index < len(pattern):
        if pattern.startswith("**", index):
            regex += ".*"
            index += 2
            if index < len(pattern) and pattern[index] == "/":
                index += 1
            continue
        char = pattern[index]
        if char == "*":
            regex += "[^/]*"
        elif char == "?":
            regex += "[^/]"
        else:
            regex += re.escape(char)
        index += 1
    regex += "$"
    return re.fullmatch(regex, value) is not None


def _pattern_covers_typical_pr_heads(pattern: str) -> bool:
    if pattern in ALL_BRANCH_GLOBS:
        return True
    return any(_github_glob_match(pattern, head) for head in TYPICAL_PR_HEADS)


def _push_matches_all_heads(event: TriggerEvent) -> bool:
    if event.tags and not event.branches and event.branches_ignore is None:
        return False
    if event.branches_ignore is not None and event.branches is None:
        return True
    if event.branches is None:
        return True
    return any(_pattern_covers_typical_pr_heads(branch) for branch in event.branches)


def _paths_overlap(left: TriggerEvent, right: TriggerEvent) -> bool:
    if left.paths is None or right.paths is None:
        return True
    if any(_is_glob(path) for path in (*left.paths, *right.paths)):
        return True
    return bool(set(left.paths) & set(right.paths))


def _security_coverage_workflow(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in SECURITY_COVERAGE_MARKERS)


def _parse_filter_mapping(
    event_name: str,
    pairs: list[tuple[str, str]],
) -> tuple[TriggerEvent | None, str | None]:
    filters: dict[str, tuple[str, ...] | None] = {}
    for key, raw in pairs:
        if key not in KNOWN_FILTER_KEYS:
            return None, f"unsupported trigger filter '{key}'"
        if key in SKIP_NESTED_FILTER_KEYS:
            continue
        value = _strip_comment(raw)
        if key == "cron":
            if not value:
                return None, "opaque schedule cron"
            filters.setdefault("crons", ())
            filters["crons"] = tuple([*(filters["crons"] or ()), _unquote(value)])
            continue
        if not value:
            if key in SKIP_NESTED_FILTER_KEYS:
                continue
            return None, f"opaque {key} filter"
        sequence = _flow_sequence(value)
        if sequence is None:
            return None, f"opaque {key} filter"
        filters[key.replace("-", "_")] = tuple(sequence)
    return (
        TriggerEvent(
            name=event_name,
            types=filters.get("types"),
            branches=filters.get("branches"),
            branches_ignore=filters.get("branches_ignore"),
            paths=filters.get("paths"),
            paths_ignore=filters.get("paths_ignore"),
            tags=filters.get("tags"),
            tags_ignore=filters.get("tags_ignore"),
            workflows=filters.get("workflows"),
            crons=filters.get("crons"),
        ),
        None,
    )


def _parse_event_block(
    event_name: str,
    inline: str,
    child_lines: list[str],
) -> tuple[TriggerEvent | None, str | None]:
    value = _strip_comment(inline)
    if value:
        if _is_opaque_fragment(value):
            return None, "opaque workflow trigger configuration"
        if value in {"~", "null", "{}", "true", "false"}:
            return TriggerEvent(name=event_name), None
        mapping = _flow_mapping(value)
        if mapping is not None:
            return _parse_filter_mapping(event_name, mapping)
        sequence = _flow_sequence(value)
        if sequence is not None and event_name not in {"schedule"}:
            return None, "opaque workflow trigger configuration"
        return None, "opaque workflow trigger configuration"

    if event_name in MANUAL_EVENTS:
        return TriggerEvent(name=event_name), None

    filters: dict[str, tuple[str, ...] | None] = {}
    direct = _direct_children(child_lines)
    if direct is None:
        return None, "opaque workflow trigger configuration"
    if not direct:
        return TriggerEvent(name=event_name), None

    for offset, line in direct:
        parsed = FANOUT_CHILD_KEY_RE.match(line)
        if parsed is None:
            if event_name == "schedule" and FANOUT_SEQUENCE_ITEM_RE.match(line):
                item = _strip_comment(FANOUT_SEQUENCE_ITEM_RE.match(line).group("value"))
                nested = _nested_block(child_lines, offset, _indent(line))
                cron_inline = ""
                if item.startswith("cron:"):
                    cron_inline = item.partition(":")[2].strip()
                crons, error = _parse_string_list(cron_inline, nested, "cron")
                if error or not crons:
                    # Sequence item is a mapping; read nested cron key.
                    cron_values: list[str] = []
                    nested_direct = _direct_children([line, *nested]) if item.endswith(":") else _direct_children(nested)
                    if item.endswith(":") and nested_direct is None:
                        nested_direct = _direct_children(nested)
                    sources = nested if not item.endswith(":") else nested
                    for nested_line in sources:
                        stripped = nested_line.strip()
                        if stripped.startswith("cron:") or stripped.startswith("'cron':") or stripped.startswith('"cron":'):
                            cron_values.append(_unquote(_strip_comment(stripped.partition(":")[2].strip())))
                    if not cron_values:
                        return None, "opaque schedule cron"
                    filters["crons"] = tuple([*(filters.get("crons") or ()), *cron_values])
                    continue
                filters["crons"] = tuple([*(filters.get("crons") or ()), *crons])
                continue
            return None, "unsupported workflow trigger syntax"
        key = _unquote(parsed.group("key"))
        rest = parsed.group("rest") or ""
        if key not in KNOWN_FILTER_KEYS:
            return None, f"unsupported trigger filter '{key}'"
        nested = _nested_block(child_lines, offset, _indent(line))
        if key in SKIP_NESTED_FILTER_KEYS:
            continue
        if key == "cron":
            cron_value = _strip_comment(rest)
            if not cron_value:
                return None, "opaque schedule cron"
            filters["crons"] = tuple([*(filters.get("crons") or ()), _unquote(cron_value)])
            continue
        values, error = _parse_string_list(rest, nested, key)
        if error:
            return None, error
        filters[key.replace("-", "_")] = values

    if event_name == "schedule" and not filters.get("crons"):
        return None, "opaque schedule cron"

    return (
        TriggerEvent(
            name=event_name,
            types=filters.get("types"),
            branches=filters.get("branches"),
            branches_ignore=filters.get("branches_ignore"),
            paths=filters.get("paths"),
            paths_ignore=filters.get("paths_ignore"),
            tags=filters.get("tags"),
            tags_ignore=filters.get("tags_ignore"),
            workflows=filters.get("workflows"),
            crons=filters.get("crons"),
        ),
        None,
    )


def _parse_on_mapping_children(
    name: str,
    child_lines: list[str],
) -> tuple[tuple[TriggerEvent, ...] | None, list[str]]:
    direct = _direct_children(child_lines)
    if direct is None:
        return None, [f"{name}: opaque workflow trigger configuration"]
    if not direct:
        return None, [f"{name}: empty workflow trigger configuration"]

    events: list[TriggerEvent] = []
    seen: set[str] = set()
    for offset, line in direct:
        if _is_opaque_fragment(line.strip()):
            return None, [f"{name}: opaque workflow trigger configuration"]
        sequence_item = FANOUT_SEQUENCE_ITEM_RE.match(line)
        parsed = FANOUT_CHILD_KEY_RE.match(line)
        if sequence_item is not None and (parsed is None or line.lstrip().startswith("- ")):
            event_name = _unquote(_strip_comment(sequence_item.group("value")))
            if not IDENTIFIER_RE.fullmatch(event_name):
                return None, [f"{name}: opaque workflow trigger configuration"]
            if event_name in seen:
                return None, [f"{name}: duplicate '{event_name}' trigger"]
            seen.add(event_name)
            events.append(TriggerEvent(name=event_name))
            continue
        if parsed is None:
            return None, [f"{name}: unsupported workflow trigger syntax"]
        event_name = _unquote(parsed.group("key"))
        if not IDENTIFIER_RE.fullmatch(event_name):
            return None, [f"{name}: opaque workflow trigger configuration"]
        if event_name in seen:
            return None, [f"{name}: duplicate '{event_name}' trigger"]
        seen.add(event_name)
        nested = _nested_block(child_lines, offset, _indent(line))
        event, error = _parse_event_block(event_name, parsed.group("rest") or "", nested)
        if error or event is None:
            return None, [f"{name}: {error or 'opaque workflow trigger configuration'}"]
        events.append(event)
    return tuple(events), []


def _parse_on_inline(
    name: str,
    value: str,
) -> tuple[tuple[TriggerEvent, ...] | None, list[str]]:
    if _is_opaque_fragment(value):
        return None, [f"{name}: opaque workflow trigger configuration"]
    scalar = _unquote(value)
    if IDENTIFIER_RE.fullmatch(scalar):
        return (TriggerEvent(name=scalar),), []
    sequence = _flow_sequence(value)
    if sequence is not None:
        events: list[TriggerEvent] = []
        seen: set[str] = set()
        for item in sequence:
            if not IDENTIFIER_RE.fullmatch(item):
                return None, [f"{name}: opaque workflow trigger configuration"]
            if item in seen:
                return None, [f"{name}: duplicate '{item}' trigger"]
            seen.add(item)
            events.append(TriggerEvent(name=item))
        return tuple(events), []
    mapping = _flow_mapping(value)
    if mapping is None:
        return None, [f"{name}: opaque workflow trigger configuration"]
    events: list[TriggerEvent] = []
    seen: set[str] = set()
    for key, rest in mapping:
        if not IDENTIFIER_RE.fullmatch(key):
            return None, [f"{name}: opaque workflow trigger configuration"]
        if key in seen:
            return None, [f"{name}: duplicate '{key}' trigger"]
        seen.add(key)
        event, error = _parse_event_block(key, rest, [])
        if error or event is None:
            return None, [f"{name}: {error or 'opaque workflow trigger configuration'}"]
        events.append(event)
    return tuple(events), []


def _routed_event_names(text: str) -> tuple[str, ...]:
    return tuple(sorted({match.group("event") for match in FANOUT_EVENT_NAME_EQ_RE.finditer(text)}))


def parse_triggers_from_text(name: str, text: str) -> tuple[TriggerFanoutRecord | None, list[str]]:
    lines = text.splitlines()
    matches = _top_level_matches(lines, FANOUT_ON_KEY_RE)
    if not matches:
        return None, [f"{name}: missing top-level on: trigger block"]
    if len(matches) > 1:
        return None, [f"{name}: multiple top-level on: declarations are forbidden"]

    index, match = matches[0]
    inline = _strip_comment(match.group("value"))
    if inline:
        events, findings = _parse_on_inline(name, inline)
    else:
        events, findings = _parse_on_mapping_children(name, _block_children(lines, index))
    if events is None:
        return None, findings

    routed = _routed_event_names(text)
    record = TriggerFanoutRecord(
        workflow=name,
        events=events,
        routed_event_names=routed,
        security_coverage=_security_coverage_workflow(name),
        dispatcher=name in DISPATCHER_WORKFLOWS or len(routed) >= 3,
    )
    return record, []


def _event_map(record: TriggerFanoutRecord) -> dict[str, TriggerEvent]:
    return {event.name: event for event in record.events}


def classify_fanout(record: TriggerFanoutRecord) -> list[FanoutFinding]:
    findings: list[FanoutFinding] = []
    events = _event_map(record)
    names = set(events)

    pull_request = events.get("pull_request")
    push = events.get("push")
    if pull_request is not None and push is not None and _paths_overlap(pull_request, push):
        if _push_matches_all_heads(push):
            if record.security_coverage:
                findings.append(
                    FanoutFinding(
                        workflow=record.workflow,
                        kind="coverage",
                        run_class="security_every_ref_push_and_pull_request",
                        message=(
                            "unconstrained push overlaps pull_request; retained so fork "
                            "PRs and every-ref security scans stay covered"
                        ),
                    )
                )
            else:
                findings.append(
                    FanoutFinding(
                        workflow=record.workflow,
                        kind="avoidable",
                        run_class="same_repo_head_push_and_pull_request",
                        message=(
                            "unconstrained push overlaps pull_request; same-repo PR heads "
                            "would emit a duplicate run class. Narrow push to protected "
                            "branches and keep pull_request for fork coverage"
                        ),
                    )
                )
        else:
            protected = bool(push.branches) and set(push.branches or ()) <= PROTECTED_BRANCHES
            findings.append(
                FanoutFinding(
                    workflow=record.workflow,
                    kind="coverage",
                    run_class=(
                        "protected_push_and_pull_request"
                        if protected
                        else "named_branch_push_and_pull_request"
                    ),
                    message=(
                        "push is limited to named/protected branches while pull_request "
                        "covers forks; this overlap is security coverage, not waste"
                    ),
                )
            )

    if pull_request is not None and pull_request.types:
        noisy = tuple(sorted(type_name for type_name in pull_request.types if type_name in NOISY_PR_TYPES))
        if noisy and not record.dispatcher:
            findings.append(
                FanoutFinding(
                    workflow=record.workflow,
                    kind="estimated",
                    run_class="metadata_pr_rerun",
                    message=(
                        "pull_request types "
                        + ", ".join(noisy)
                        + " re-run the workflow on metadata-only PR changes"
                    ),
                )
            )

    if (names & REVIEW_EVENTS) and "pull_request" in names and not record.dispatcher:
        findings.append(
            FanoutFinding(
                workflow=record.workflow,
                kind="avoidable",
                run_class="review_event_ci_rerun",
                message=(
                    "pull_request plus review events re-run the same workflow on every "
                    "review without an event-name dispatcher split"
                ),
            )
        )

    if "schedule" in names and "push" in names:
        findings.append(
            FanoutFinding(
                workflow=record.workflow,
                kind="coverage",
                run_class="schedule_and_push_overlap",
                message=(
                    "schedule plus push overlap is retained so idle/security coverage "
                    "still runs when no push arrives"
                ),
            )
        )

    return findings


def audit_from_text(name: str, text: str) -> FanoutAudit:
    record, parse_findings = parse_triggers_from_text(name, text)
    findings = [
        FanoutFinding(
            workflow=name,
            kind="opaque",
            run_class="opaque_yaml",
            message=message.partition(": ")[2] if message.startswith(f"{name}: ") else message,
        )
        for message in parse_findings
    ]
    records = ()
    if record is not None:
        records = (record,)
        findings.extend(classify_fanout(record))
    return FanoutAudit(records=records, findings=tuple(findings))


def violations_from_text(name: str, text: str) -> list[str]:
    return audit_from_text(name, text).violations()


def violations(path: Path) -> list[str]:
    if path.is_symlink():
        return [
            FanoutFinding(
                workflow=path.name,
                kind="opaque",
                run_class="opaque_yaml",
                message="workflow files must not be symlinks",
            ).render()
        ]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [
            FanoutFinding(
                workflow=path.name,
                kind="opaque",
                run_class="opaque_yaml",
                message=f"cannot inspect workflow trigger-fanout: {type(exc).__name__}",
            ).render()
        ]
    return violations_from_text(path.name, text)


def repository_audit(workflow_dir: Path | None = None) -> FanoutAudit:
    directory = WORKFLOW_DIR if workflow_dir is None else workflow_dir
    if directory.is_symlink():
        finding = FanoutFinding(
            workflow="<workflows>",
            kind="opaque",
            run_class="opaque_yaml",
            message="GitHub Actions workflow directory must not be a symlink",
        )
        return FanoutAudit(records=(), findings=(finding,))

    workflows = sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])
    if not workflows:
        finding = FanoutFinding(
            workflow="<workflows>",
            kind="opaque",
            run_class="opaque_yaml",
            message="No GitHub Actions workflows found.",
        )
        return FanoutAudit(records=(), findings=(finding,))

    records: list[TriggerFanoutRecord] = []
    findings: list[FanoutFinding] = []
    for path in workflows:
        if path.is_symlink():
            findings.append(
                FanoutFinding(
                    workflow=path.name,
                    kind="opaque",
                    run_class="opaque_yaml",
                    message="workflow files must not be symlinks",
                )
            )
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            findings.append(
                FanoutFinding(
                    workflow=path.name,
                    kind="opaque",
                    run_class="opaque_yaml",
                    message=f"cannot inspect workflow trigger-fanout: {type(exc).__name__}",
                )
            )
            continue
        audit = audit_from_text(path.name, text)
        records.extend(audit.records)
        findings.extend(audit.findings)
    findings.sort(key=lambda item: (item.kind, item.workflow, item.run_class, item.message))
    return FanoutAudit(records=tuple(records), findings=tuple(findings))


def repository_violations(workflow_dir: Path | None = None) -> list[str]:
    return repository_audit(workflow_dir).violations()


def main() -> int:
    audit = repository_audit()
    violations_found = audit.violations()
    estimated = audit.estimated_avoidable_run_classes()
    coverage = [finding for finding in audit.findings if finding.kind == "coverage"]
    workflows = workflow_files() if WORKFLOW_DIR.exists() else []

    if violations_found:
        print("GitHub Actions trigger-fanout audit failed:", file=sys.stderr)
        for finding in violations_found:
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print(
        f"Trigger-fanout gate passed for {len(workflows)} workflow files: "
        f"{len(coverage)} coverage-preserving overlaps, "
        f"{len(estimated)} estimated avoidable run classes, "
        "0 opaque YAML failures."
    )
    for finding in coverage:
        if finding.run_class == "security_every_ref_push_and_pull_request":
            print(f"  coverage: {finding.render()}")
    for finding in estimated:
        print(f"  estimated: {finding.render()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())