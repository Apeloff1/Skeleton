"""Static GitHub Actions policy gate."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys

if __package__:
    from .check_workflow_container_security import violations as container_runtime_violations
    from .check_workflow_input_security import (
        _flow_mapping_entries,
        _flow_style_steps,
        _run_fragments as hardened_run_fragments,
        violations as input_boundary_violations,
    )
else:
    from check_workflow_container_security import violations as container_runtime_violations
    from check_workflow_input_security import (
        _flow_mapping_entries,
        _flow_style_steps,
        _run_fragments as hardened_run_fragments,
        violations as input_boundary_violations,
    )

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
SHA40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
USES_RE = re.compile(
    r"^\s*(?:-\s*)?(?:\{\s*)?(?:uses|'uses'|\"uses\")\s*:\s*[\"']?([^\"'\s,}#]+)"
)
FLOW_USES_ENTRY_RE = re.compile(
    r"^(?:uses|'uses'|\"uses\")\s*:\s*[\"']?([^\"'\s,}#]+)"
)
EXPRESSION_RE = re.compile(r"\$\{\{(?P<body>.*?)\}\}", re.DOTALL)
PERSIST_FALSE_RE = re.compile(
    r"(?:persist-credentials|'persist-credentials'|\"persist-credentials\")\s*:\s*"
    r"(?:false|['\"]false['\"])(?=\s*[,}#]|\s*$)",
    re.IGNORECASE,
)
PERMISSION_ENTRY_RE = re.compile(
    r"^\s+['\"]?(?P<scope>[A-Za-z0-9_-]+)['\"]?\s*:\s*"
    r"(?P<value>read|write|none)\s*(?:#.*)?$",
    re.IGNORECASE,
)
TOP_LEVEL_ON_RE = re.compile(r"^(?:on|'on'|\"on\")\s*:\s*(?P<value>.*)$")
NODE_PROPERTIES_RE = re.compile(
    r"^(?:(?:[!&][^\s#]+)\s+)*(?P<value>.*)$"
)
PULL_REQUEST_TARGET_KEY_RE = re.compile(
    r"^\s*(?:pull_request_target|'pull_request_target'|\"pull_request_target\")\s*:"
)
PULL_REQUEST_TARGET_SEQUENCE_RE = re.compile(
    r"^\s*-\s*(?:pull_request_target|'pull_request_target'|\"pull_request_target\")\s*(?:#.*)?$"
)
CHECKOUT_ACTION = "actions/checkout@"
FORBIDDEN_TRIGGER = "pull_request_target"

# pull_request_target remains forbidden by default. The obsolete-run drainer is
# the sole exception because it needs Actions write access while deliberately
# executing only default-branch control-plane code. The exception is content-
# addressed: any byte-level workflow change automatically revokes the exception
# until the security policy is reviewed and this digest is deliberately updated.
TRUSTED_PULL_REQUEST_TARGET_SHA256 = {
    "pr-obsolete-run-drain.yml": (
        "dff208e01fcb638184f67b1029014653a000c43908467a60f18f225976b7634d"
    ),
}

UNTRUSTED_RUN_CONTEXTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pull request title/body", re.compile(r"\bgithub\.event\.pull_request\.(?:title|body)\b")),
    ("pull request head ref/label", re.compile(r"\bgithub\.event\.pull_request\.head\.(?:ref|label)\b")),
    ("issue title/body", re.compile(r"\bgithub\.event\.issue\.(?:title|body)\b")),
    ("issue comment body", re.compile(r"\bgithub\.event\.comment\.body\b")),
    ("review body", re.compile(r"\bgithub\.event\.(?:review|review_comment)\.body\b")),
    ("head commit message", re.compile(r"\bgithub\.event\.head_commit\.message\b")),
    ("head ref", re.compile(r"\bgithub\.head_ref\b")),
)


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])


def _is_local(reference: str) -> bool:
    return reference.startswith("./")


def _container_violation(reference: str) -> str | None:
    if not reference.startswith("docker://"):
        return None
    target = reference.removeprefix("docker://")
    if "@sha256:" not in target:
        return "container action must be pinned to an immutable sha256 digest"
    image, digest = target.rsplit("@sha256:", 1)
    if not image or not SHA256_RE.fullmatch(digest):
        return "container action has an invalid sha256 digest pin"
    return None


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _checkout_credentials_disabled(lines: list[str], uses_index: int) -> bool:
    base_indent = _indent_width(lines[uses_index])
    index = uses_index + 1
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped:
            indent = _indent_width(line)
            if indent < base_indent or (indent == base_indent and stripped.startswith("- ")):
                break
            if PERSIST_FALSE_RE.search(line):
                return True
        index += 1
    return False


def _action_reference_findings(
    path_name: str,
    number: int,
    reference: str,
    *,
    checkout_hardened: bool,
) -> list[str]:
    findings: list[str] = []
    if reference.startswith(CHECKOUT_ACTION) and not checkout_hardened:
        findings.append(
            f"{path_name}:{number}: actions/checkout must set persist-credentials: false"
        )
    if _is_local(reference):
        return findings
    if reference.startswith("docker://"):
        container_violation = _container_violation(reference)
        if container_violation:
            findings.append(f"{path_name}:{number}: {container_violation}: {reference}")
        return findings
    if "@" not in reference:
        findings.append(
            f"{path_name}:{number}: action reference must be pinned to an immutable commit SHA: {reference}"
        )
        return findings
    _action, revision = reference.rsplit("@", 1)
    if not SHA40_RE.fullmatch(revision):
        findings.append(
            f"{path_name}:{number}: action reference is not pinned to a 40-character commit SHA: {reference}"
        )
    return findings


def _top_level_permission_violations(
    lines: list[str], path_name: str
) -> tuple[bool, list[str]]:
    findings: list[str] = []
    has_top_level = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if line != stripped or not stripped.startswith("permissions:"):
            continue
        has_top_level = True
        number = index + 1
        declaration = stripped.split("#", 1)[0].strip()
        inline = declaration.partition(":")[2].strip().lower()
        if inline in {"write-all", "write"}:
            findings.append(
                f"{path_name}:{number}: workflow-wide write permissions are forbidden; grant write scopes only to the job that needs them"
            )
            continue
        if inline == "read-all":
            findings.append(
                f"{path_name}:{number}: workflow-wide read-all is forbidden; declare only required read scopes"
            )
            continue
        if inline:
            if inline != "{}":
                findings.append(
                    f"{path_name}:{number}: unsupported top-level permissions scalar; use a scoped mapping or {{}}"
                )
            continue
        child_index = index + 1
        while child_index < len(lines):
            child = lines[child_index]
            if child.strip() and _indent_width(child) == 0:
                break
            match = PERMISSION_ENTRY_RE.match(child)
            if match and match.group("value").lower() == "write":
                findings.append(
                    f"{path_name}:{child_index + 1}: workflow-wide {match.group('scope')}: write is forbidden; move elevation to the specific job"
                )
            child_index += 1
    return has_top_level, findings


def _yaml_key_name(entry: str) -> str:
    key = entry.partition(":")[0].strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in {"'", '"'}:
        return key[1:-1]
    return key


def _strip_node_properties(value: str) -> str:
    """Remove YAML tag/anchor properties that precede an inline node value."""
    match = NODE_PROPERTIES_RE.fullmatch(value.strip())
    if match is None:
        return value.strip()
    return match.group("value").strip()


def _approved_pull_request_target(path_name: str, text: str) -> bool:
    expected = TRUSTED_PULL_REQUEST_TARGET_SHA256.get(path_name)
    if expected is None:
        return False
    actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return actual == expected


def _forbidden_trigger_violations(
    lines: list[str],
    path_name: str,
    *,
    allow_pull_request_target: bool = False,
) -> list[str]:
    findings: list[str] = []
    for index, line in enumerate(lines):
        if line != line.lstrip(" "):
            continue
        match = TOP_LEVEL_ON_RE.match(line)
        if not match:
            continue

        number = index + 1
        value = match.group("value").split("#", 1)[0].strip()
        if value:
            value = _strip_node_properties(value)
            if value.startswith("*"):
                findings.append(
                    f"{path_name}:{number}: aliased workflow trigger configuration is forbidden because the security gate cannot resolve the referenced events"
                )
                continue

            scalar = value
            if len(scalar) >= 2 and scalar[0] == scalar[-1] and scalar[0] in {"'", '"'}:
                scalar = scalar[1:-1]
            if scalar == FORBIDDEN_TRIGGER:
                if not allow_pull_request_target:
                    findings.append(f"{path_name}:{number}: pull_request_target is forbidden")
                continue

            if value.startswith("{"):
                if any(
                    _yaml_key_name(entry) == FORBIDDEN_TRIGGER
                    for entry in _flow_mapping_entries(value)
                ) and not allow_pull_request_target:
                    findings.append(f"{path_name}:{number}: pull_request_target is forbidden")
                continue

            if value.startswith("[") and value.endswith("]"):
                for item in value[1:-1].split(","):
                    event = item.strip()
                    if len(event) >= 2 and event[0] == event[-1] and event[0] in {"'", '"'}:
                        event = event[1:-1]
                    if event == FORBIDDEN_TRIGGER:
                        if not allow_pull_request_target:
                            findings.append(
                                f"{path_name}:{number}: pull_request_target is forbidden"
                            )
                        break
                continue
            continue

        children: list[tuple[int, str, int]] = []
        child_index = index + 1
        while child_index < len(lines):
            child = lines[child_index]
            stripped_child = child.strip()
            indent = _indent_width(child)
            if stripped_child and indent == 0:
                break
            if stripped_child and not stripped_child.startswith("#"):
                children.append((child_index + 1, child, indent))
            child_index += 1
        if not children:
            continue
        direct_indent = min(indent for _line_number, _child, indent in children)
        for child_number, child, indent in children:
            if indent != direct_indent:
                continue
            if PULL_REQUEST_TARGET_KEY_RE.match(child) or PULL_REQUEST_TARGET_SEQUENCE_RE.match(child):
                if not allow_pull_request_target:
                    findings.append(
                        f"{path_name}:{child_number}: pull_request_target is forbidden"
                    )
    return findings


def _untrusted_expression(fragment: str) -> str | None:
    for expression in EXPRESSION_RE.finditer(fragment):
        body = expression.group("body")
        for label, pattern in UNTRUSTED_RUN_CONTEXTS:
            if pattern.search(body):
                return label
    return None


def violations(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{path}: read failure: {exc}"]

    findings: list[str] = []
    findings.extend(input_boundary_violations(path))
    findings.extend(container_runtime_violations(path))
    lines = text.splitlines()
    has_top_level_permissions, permission_findings = _top_level_permission_violations(
        lines, path.name
    )
    findings.extend(permission_findings)
    findings.extend(
        _forbidden_trigger_violations(
            lines,
            path.name,
            allow_pull_request_target=_approved_pull_request_target(path.name, text),
        )
    )

    for number, fragment in _flow_style_steps(lines):
        if any(USES_RE.match(source_line) for source_line in fragment.splitlines()):
            continue
        for entry in _flow_mapping_entries(fragment):
            match = FLOW_USES_ENTRY_RE.match(entry.strip())
            if not match:
                continue
            reference = match.group(1).strip("\"'")
            findings.extend(
                _action_reference_findings(
                    path.name,
                    number,
                    reference,
                    checkout_hardened=bool(PERSIST_FALSE_RE.search(fragment)),
                )
            )

    for index, line in enumerate(lines):
        number = index + 1
        if re.match(r"^\s*permissions\s*:\s*write-all\s*$", line):
            findings.append(f"{path.name}:{number}: write-all permissions are forbidden")
        match = USES_RE.match(line)
        if not match:
            continue
        reference = match.group(1).strip("\"'")
        findings.extend(
            _action_reference_findings(
                path.name,
                number,
                reference,
                checkout_hardened=_checkout_credentials_disabled(lines, index),
            )
        )

    for number, fragment in hardened_run_fragments(lines):
        label = _untrusted_expression(fragment)
        if label:
            findings.append(
                f"{path.name}:{number}: direct {label} interpolation in run shell is forbidden; pass it through env instead"
            )

    if not has_top_level_permissions:
        findings.append(f"{path.name}: missing explicit top-level permissions block")
    return findings


def main() -> int:
    findings: list[str] = []
    workflows = workflow_files()
    if not workflows:
        print("No GitHub Actions workflows found.", file=sys.stderr)
        return 1
    for path in workflows:
        findings.extend(violations(path))
    if findings:
        print("GitHub Actions workflow security violations detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print(f"Workflow security gate passed for {len(workflows)} workflow files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
