"""Fail-closed GitHub Actions concurrency-key collision audit.

GitHub concurrency groups are repository-global, not workflow-scoped. Two
workflows that share a group string cancel or serialize each other even when
their filenames differ. A single workflow whose group fallback mixes PR numbers
with branch names can also collapse unrelated runs into one slot.

This gate uses only the Python standard library so it can run before project
dependencies are installed. It parses the small concurrency and trigger surface
we permit and fails closed on opaque YAML instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

CONCURRENCY_KEY_RE = re.compile(
    r"^(?P<indent> *)(?:concurrency|'concurrency'|\"concurrency\")\s*:\s*(?P<value>.*)$"
)
ON_KEY_RE = re.compile(r"^(?:on|'on'|\"on\")\s*:\s*(?P<value>.*)$")
GROUP_KEY_RE = re.compile(
    r"^(?P<indent> +)(?:group|'group'|\"group\")\s*:\s*(?P<value>.*)$"
)
CANCEL_KEY_RE = re.compile(
    r"^(?P<indent> +)(?:cancel-in-progress|'cancel-in-progress'|\"cancel-in-progress\")"
    r"\s*:\s*(?P<value>.*)$"
)
CHILD_KEY_RE = re.compile(
    r"^(?P<indent> +)(?:- )?(?P<key>['\"]?[A-Za-z][A-Za-z0-9_-]*['\"]?)\s*(?::(?P<rest>.*))?$"
)
EXPRESSION_RE = re.compile(r"\$\{\{(?P<body>.*?)\}\}", re.DOTALL)
NUMERIC_RE = re.compile(r"\bgithub\.event\.(?P<kind>pull_request|issue)\.number\b")
REF_NAME_RE = re.compile(
    r"\b(?:github\.(?:ref_name|head_ref|base_ref)|"
    r"github\.event\.workflow_run\.head_branch|"
    r"github\.event\.pull_request\.head\.ref|"
    r"inputs\.[A-Za-z][A-Za-z0-9_]*)\b"
)
SAFE_IDENTITY_RE = re.compile(
    r"\bgithub\.(?:ref|sha|repository|workflow|run_id|event_name)\b"
    r"|\bgithub\.event\.workflow_run\.(?:workflow_id|head_sha)\b"
)
LITERAL_RE = re.compile(r"^['\"][^'\"]*['\"]$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
OPAQUE_CHARS = frozenset("()[]*&!")

PR_EVENTS = frozenset(
    {
        "pull_request",
        "pull_request_review",
        "pull_request_review_comment",
        "pull_request_target",
    }
)
ISSUE_EVENTS = frozenset({"issues", "issue_comment"})
NUMERIC_EVENTS = PR_EVENTS | ISSUE_EVENTS


@dataclass(frozen=True)
class ConcurrencyRecord:
    name: str
    prefix: str
    template: str


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _strip_comment(value: str) -> str:
    return value.split("#", 1)[0].strip()


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _yaml_key(entry: str) -> str:
    key = entry.partition(":")[0].strip()
    return _unquote(key)


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


def _flow_keys(value: str) -> list[str] | None:
    if not (value.startswith("{") and value.endswith("}")):
        return None
    keys: list[str] = []
    depth = 0
    token: list[str] = []
    in_single = False
    in_double = False
    for char in value[1:-1]:
        if in_single:
            if char == "'":
                in_single = False
            token.append(char)
            continue
        if in_double:
            if char == '"':
                in_double = False
            token.append(char)
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
                keys.append(_yaml_key(entry))
            token = []
            continue
        token.append(char)
    entry = "".join(token).strip()
    if entry:
        keys.append(_yaml_key(entry))
    if any(not IDENTIFIER_RE.fullmatch(key) for key in keys):
        return None
    return keys


def _sequence_items(value: str) -> list[str] | None:
    if not (value.startswith("[") and value.endswith("]")):
        return None
    items: list[str] = []
    for raw in value[1:-1].split(","):
        item = _unquote(raw.strip())
        if not item:
            continue
        if not IDENTIFIER_RE.fullmatch(item):
            return None
        items.append(item)
    return items


def _trigger_events(name: str, lines: list[str]) -> tuple[frozenset[str] | None, list[str]]:
    matches = _top_level_matches(lines, ON_KEY_RE)
    if not matches:
        return None, [f"{name}: missing top-level on: trigger block"]
    if len(matches) > 1:
        return None, [f"{name}: multiple top-level on: declarations are forbidden"]

    index, match = matches[0]
    value = _strip_comment(match.group("value"))
    if value:
        if any(char in value for char in "*&!"):
            return None, [f"{name}:{index + 1}: opaque workflow trigger configuration"]
        scalar = _unquote(value)
        if IDENTIFIER_RE.fullmatch(scalar):
            return frozenset({scalar}), []
        sequence = _sequence_items(value)
        if sequence is not None:
            return frozenset(sequence), []
        mapping = _flow_keys(value)
        if mapping is not None:
            return frozenset(mapping), []
        return None, [f"{name}:{index + 1}: opaque workflow trigger configuration"]

    events: list[str] = []
    children = [child for child in _block_children(lines, index) if child.strip() and not child.strip().startswith("#")]
    if not children:
        return None, [f"{name}:{index + 1}: empty workflow trigger configuration"]
    direct = min(_indent(child) for child in children)
    for child in children:
        if _indent(child) != direct:
            continue
        parsed = CHILD_KEY_RE.match(child)
        if parsed is None:
            return None, [f"{name}: unsupported workflow trigger syntax"]
        event = _unquote(parsed.group("key"))
        if not IDENTIFIER_RE.fullmatch(event):
            return None, [f"{name}: opaque workflow trigger configuration"]
        events.append(event)
    if not events:
        return None, [f"{name}: opaque workflow trigger configuration"]
    return frozenset(events), []


def _split_or_chain(body: str) -> list[str] | None:
    compact = " ".join(body.split())
    if not compact or any(char in compact for char in OPAQUE_CHARS):
        return None
    parts = [part.strip() for part in compact.split("||")]
    if not parts or any(not part for part in parts):
        return None
    return parts


def _classify_part(part: str) -> str:
    if LITERAL_RE.fullmatch(part):
        return "literal"
    if NUMERIC_RE.search(part):
        return "numeric"
    if REF_NAME_RE.search(part):
        return "ref_name"
    if SAFE_IDENTITY_RE.search(part):
        return "safe"
    return "opaque"


def _group_findings(
    name: str,
    template: str,
    events: frozenset[str],
) -> tuple[str | None, list[str]]:
    findings: list[str] = []
    expressions = list(EXPRESSION_RE.finditer(template))
    prefix = template[: expressions[0].start()] if expressions else template
    if not prefix:
        findings.append(
            f"{name}: concurrency group must include a unique literal workflow identity prefix"
        )
        return None, findings

    has_event_name = "github.event_name" in template
    numeric_kinds: set[str] = set()
    has_safe_or_literal = False

    for match in expressions:
        parts = _split_or_chain(match.group("body"))
        if parts is None:
            findings.append(f"{name}: opaque concurrency group expression")
            return None, findings
        chain_kinds = [_classify_part(part) for part in parts]
        if "opaque" in chain_kinds:
            findings.append(f"{name}: unsupported concurrency group identity '{match.group('body').strip()}'")
            return None, findings
        if "numeric" in chain_kinds and "ref_name" in chain_kinds:
            findings.append(
                f"{name}: concurrency group mixes pull/issue numbers with ref_name identity; "
                "PR 123 and branch 123 would share a slot"
            )
        if "ref_name" in chain_kinds and not has_event_name and "safe" not in chain_kinds:
            pr_push_only = bool(events) and events.issubset({"pull_request", "push"})
            if "||" in match.group("body") and not pr_push_only:
                findings.append(
                    f"{name}: branch-name concurrency fallbacks must include github.event_name "
                    "so schedule/push/workflow_run runs cannot collapse onto one another"
                )
        for part, kind in zip(parts, chain_kinds, strict=True):
            if kind == "numeric":
                found = NUMERIC_RE.search(part)
                if found is not None:
                    numeric_kinds.add(found.group("kind"))
            if kind in {"safe", "literal"}:
                has_safe_or_literal = True

    leftover_events = events - NUMERIC_EVENTS
    if numeric_kinds and leftover_events and not has_safe_or_literal:
        findings.append(
            f"{name}: concurrency group uses a pull/issue number without a safe fallback; "
            f"events {sorted(leftover_events)} would share an empty group"
        )
    if (
        "issue" in numeric_kinds
        and (events & PR_EVENTS)
        and "pull_request" not in numeric_kinds
        and not has_safe_or_literal
    ):
        findings.append(
            f"{name}: pull_request runs do not populate github.event.issue.number; "
            "include github.event.pull_request.number or another safe fallback"
        )
    if (
        "pull_request" in numeric_kinds
        and (events & ISSUE_EVENTS)
        and "issue" not in numeric_kinds
        and not has_safe_or_literal
    ):
        findings.append(
            f"{name}: issue events do not populate github.event.pull_request.number; "
            "include github.event.issue.number or another safe fallback"
        )

    return prefix, findings


def _concurrency_findings(name: str, lines: list[str], events: frozenset[str]) -> tuple[ConcurrencyRecord | None, list[str]]:
    matches = _top_level_matches(lines, CONCURRENCY_KEY_RE)
    if not matches:
        return None, [f"{name}: missing top-level concurrency declaration"]
    if len(matches) > 1:
        return None, [f"{name}: multiple top-level concurrency declarations are forbidden"]

    index, match = matches[0]
    inline = _strip_comment(match.group("value"))
    if inline:
        return None, [
            f"{name}:{index + 1}: opaque/inline concurrency is forbidden; "
            "use a block mapping with group and cancel-in-progress"
        ]

    children = _block_children(lines, index)
    groups: list[str] = []
    cancels: list[str] = []
    for offset, child in enumerate(children, start=index + 2):
        stripped = child.strip()
        if not stripped or stripped.startswith("#"):
            continue
        group = GROUP_KEY_RE.match(child)
        cancel = CANCEL_KEY_RE.match(child)
        if group is not None:
            groups.append(_strip_comment(group.group("value")))
            continue
        if cancel is not None:
            cancels.append(_strip_comment(cancel.group("value")))
            continue
        return None, [f"{name}:{offset}: unsupported concurrency key; only group and cancel-in-progress are permitted"]

    findings: list[str] = []
    if len(groups) != 1:
        findings.append(f"{name}: concurrency block must declare exactly one group")
    if len(cancels) != 1:
        findings.append(f"{name}: concurrency block must declare cancel-in-progress explicitly")
    elif cancels[0] not in {"true", "false"} and not (
        cancels[0].startswith("${{") and cancels[0].endswith("}}")
    ):
        findings.append(f"{name}: cancel-in-progress must be true, false, or a GitHub expression")
    if findings or not groups:
        return None, findings

    template = _unquote(groups[0])
    if not template or any(char in template for char in "*&"):
        return None, [f"{name}: opaque concurrency group value"]

    prefix, group_findings = _group_findings(name, template, events)
    findings.extend(group_findings)
    if prefix is None:
        return None, findings
    return ConcurrencyRecord(name=name, prefix=prefix, template=template), findings


def violations_from_text(name: str, text: str) -> tuple[ConcurrencyRecord | None, list[str]]:
    lines = text.splitlines()
    events, trigger_findings = _trigger_events(name, lines)
    if events is None:
        return None, trigger_findings
    record, findings = _concurrency_findings(name, lines, events)
    return record, trigger_findings + findings


def violations(path: Path) -> tuple[ConcurrencyRecord | None, list[str]]:
    if path.is_symlink():
        return None, [f"{path.name}: workflow files must not be symlinks"]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return None, [f"{path.name}: cannot inspect workflow concurrency: {type(exc).__name__}"]
    return violations_from_text(path.name, text)


def repository_violations(workflow_dir: Path | None = None) -> list[str]:
    directory = WORKFLOW_DIR if workflow_dir is None else workflow_dir
    if directory.is_symlink():
        return ["GitHub Actions workflow directory must not be a symlink"]

    workflows = sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])
    if not workflows:
        return ["No GitHub Actions workflows found."]

    findings: list[str] = []
    records: list[ConcurrencyRecord] = []
    for path in workflows:
        record, file_findings = violations(path)
        findings.extend(file_findings)
        if record is not None:
            records.append(record)

    by_prefix: dict[str, list[str]] = {}
    by_template: dict[str, list[str]] = {}
    for record in records:
        by_prefix.setdefault(record.prefix, []).append(record.name)
        by_template.setdefault(record.template, []).append(record.name)
    for prefix, names in sorted(by_prefix.items()):
        if len(names) > 1:
            findings.append(
                f"concurrency group prefix {prefix!r} is shared by {', '.join(sorted(names))}; "
                "GitHub concurrency groups are repository-global"
            )
    for template, names in sorted(by_template.items()):
        if len(names) > 1:
            findings.append(
                f"identical concurrency group {template!r} is shared by {', '.join(sorted(names))}"
            )
    return sorted(set(findings))


def main() -> int:
    findings = repository_violations()
    if findings:
        print("GitHub Actions concurrency-key collisions detected:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1

    workflows = workflow_files()
    print(
        f"Workflow concurrency gate passed for {len(workflows)} workflow files: "
        "every workflow has an explicit unique group and no PR/ref identity collision."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
