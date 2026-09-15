"""GitHub Actions job/service container hardening policy."""
from __future__ import annotations

from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
KEY_RE_TEMPLATE = r"^(?P<indent>\s*)(?:{plain}|'(?:{plain})'|\"(?:{plain})\")\s*:\s*(?P<value>.*)$"
CONTAINER_RE = re.compile(KEY_RE_TEMPLATE.format(plain="container"))
SERVICES_RE = re.compile(KEY_RE_TEMPLATE.format(plain="services"))
IMAGE_RE = re.compile(KEY_RE_TEMPLATE.format(plain="image"))
OPTIONS_RE = re.compile(KEY_RE_TEMPLATE.format(plain="options"))
SERVICE_ENTRY_RE = re.compile(
    r"^(?P<indent>\s*)(?:[A-Za-z0-9_.-]+|'[^']+'|\"[^\"]+\")\s*:\s*(?P<value>.*)$"
)

DANGEROUS_OPTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("privileged mode", re.compile(r"(?:^|\s)--privileged(?:\s|$|=)", re.IGNORECASE)),
    ("host network namespace", re.compile(r"(?:^|\s)--network(?:=|\s+)host(?:\s|$)", re.IGNORECASE)),
    ("host PID namespace", re.compile(r"(?:^|\s)--pid(?:=|\s+)host(?:\s|$)", re.IGNORECASE)),
    ("host IPC namespace", re.compile(r"(?:^|\s)--ipc(?:=|\s+)host(?:\s|$)", re.IGNORECASE)),
    ("host UTS namespace", re.compile(r"(?:^|\s)--uts(?:=|\s+)host(?:\s|$)", re.IGNORECASE)),
    ("host user namespace", re.compile(r"(?:^|\s)--userns(?:=|\s+)host(?:\s|$)", re.IGNORECASE)),
    ("device passthrough", re.compile(r"(?:^|\s)--device(?:=|\s+)", re.IGNORECASE)),
    ("Linux capability elevation", re.compile(r"(?:^|\s)--cap-add(?:=|\s+)", re.IGNORECASE)),
    (
        "unconfined security profile",
        re.compile(
            r"(?:^|\s)--security-opt(?:=|\s+)[^\n]*(?:unconfined|seccomp=unconfined|apparmor=unconfined)",
            re.IGNORECASE,
        ),
    ),
    ("Docker daemon socket mount", re.compile(r"(?:/var/run/docker\.sock|/run/docker\.sock)", re.IGNORECASE)),
    ("host root filesystem mount", re.compile(r"(?:^|\s)(?:-v|--volume)(?:=|\s+)/:(?:[^\s]+)", re.IGNORECASE)),
    ("host root bind mount", re.compile(r"(?:^|\s)--mount(?:=|\s+)[^\n]*\bsource=/(?:,|\s|$)", re.IGNORECASE)),
)


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _scalar(raw: str) -> str:
    value = raw.strip()
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.strip()


def _immutable_image_violation(reference: str) -> str | None:
    target = _scalar(reference)
    if not target:
        return "container image reference is missing"
    if "${{" in target:
        return "dynamic container image references are forbidden; pin a literal sha256 digest"
    if "@sha256:" not in target:
        return "container image must be pinned to an immutable sha256 digest"
    image, digest = target.rsplit("@sha256:", 1)
    if not image or not SHA256_RE.fullmatch(digest):
        return "container image has an invalid sha256 digest pin"
    return None


def _dangerous_options(value: str) -> list[str]:
    options = _scalar(value)
    return [label for label, pattern in DANGEROUS_OPTION_PATTERNS if pattern.search(options)]


def _expanded_options(lines: list[str], index: int, raw: str) -> str:
    value = raw.strip()
    if value not in {"|", "|-", "|+", ">", ">-", ">+"}:
        return value
    base_indent = _indent_width(lines[index])
    chunks: list[str] = []
    child = index + 1
    while child < len(lines):
        line = lines[child]
        if line.strip() and _indent_width(line) <= base_indent:
            break
        if line.strip():
            chunks.append(line.strip())
        child += 1
    return " ".join(chunks)


def _block_end(lines: list[str], start: int, base_indent: int) -> int:
    index = start + 1
    while index < len(lines):
        line = lines[index]
        if line.strip() and _indent_width(line) <= base_indent:
            break
        index += 1
    return index


def _container_block_findings(
    lines: list[str], path_name: str, start: int, match: re.Match[str]
) -> tuple[list[str], set[int]]:
    findings: list[str] = []
    covered: set[int] = set()
    number = start + 1
    base_indent = len(match.group("indent"))
    value = match.group("value").strip()

    if value:
        if value.startswith("{"):
            findings.append(
                f"{path_name}:{number}: flow-style job container configuration is forbidden; use an auditable block mapping with a digest-pinned image"
            )
            return findings, covered
        violation = _immutable_image_violation(value)
        if violation:
            findings.append(f"{path_name}:{number}: {violation}: {_scalar(value)}")
        return findings, covered

    end = _block_end(lines, start, base_indent)
    image_seen = False
    for index in range(start + 1, end):
        line = lines[index]
        if not line.strip():
            continue
        image_match = IMAGE_RE.match(line)
        if image_match and _indent_width(line) > base_indent:
            image_seen = True
            covered.add(index)
            violation = _immutable_image_violation(image_match.group("value"))
            if violation:
                findings.append(
                    f"{path_name}:{index + 1}: {violation}: {_scalar(image_match.group('value'))}"
                )
        options_match = OPTIONS_RE.match(line)
        if options_match and _indent_width(line) > base_indent:
            covered.add(index)
            option_value = _expanded_options(lines, index, options_match.group("value"))
            for label in _dangerous_options(option_value):
                findings.append(
                    f"{path_name}:{index + 1}: job container options grant forbidden {label}"
                )
    if not image_seen:
        findings.append(f"{path_name}:{number}: job container block must declare a digest-pinned image")
    return findings, covered


def _services_block_findings(
    lines: list[str], path_name: str, start: int, match: re.Match[str]
) -> tuple[list[str], set[int]]:
    findings: list[str] = []
    covered: set[int] = set()
    number = start + 1
    base_indent = len(match.group("indent"))
    value = match.group("value").strip()
    if value and value not in {"{}", "{ }"}:
        findings.append(
            f"{path_name}:{number}: flow-style services configuration is forbidden; use block mappings with digest-pinned images"
        )
        return findings, covered
    if value:
        return findings, covered

    end = _block_end(lines, start, base_indent)
    content_lines = [
        (index, line)
        for index, line in enumerate(lines[start + 1 : end], start + 1)
        if line.strip() and not line.lstrip().startswith("#") and _indent_width(line) > base_indent
    ]
    if not content_lines:
        return findings, covered

    service_indent = min(_indent_width(line) for _index, line in content_lines)
    service_entries: list[tuple[int, re.Match[str]]] = []
    for index, line in content_lines:
        if _indent_width(line) != service_indent:
            continue
        entry_match = SERVICE_ENTRY_RE.match(line)
        if entry_match:
            service_entries.append((index, entry_match))

    for position, (service_index, service_match) in enumerate(service_entries):
        raw_value = service_match.group("value").strip()
        service_end = service_entries[position + 1][0] if position + 1 < len(service_entries) else end
        if raw_value and not raw_value.startswith("#"):
            findings.append(
                f"{path_name}:{service_index + 1}: flow-style, aliased, or scalar service container configuration is forbidden; use an auditable block mapping with a digest-pinned image"
            )
            continue
        image_seen = any(
            IMAGE_RE.match(lines[index]) and _indent_width(lines[index]) > service_indent
            for index in range(service_index + 1, service_end)
        )
        if not image_seen:
            findings.append(
                f"{path_name}:{service_index + 1}: service container block must declare a digest-pinned image"
            )

    for index in range(start + 1, end):
        line = lines[index]
        if not line.strip() or _indent_width(line) <= base_indent:
            continue
        image_match = IMAGE_RE.match(line)
        if image_match:
            covered.add(index)
            violation = _immutable_image_violation(image_match.group("value"))
            if violation:
                findings.append(
                    f"{path_name}:{index + 1}: service {violation}: {_scalar(image_match.group('value'))}"
                )
        options_match = OPTIONS_RE.match(line)
        if options_match:
            covered.add(index)
            option_value = _expanded_options(lines, index, options_match.group("value"))
            for label in _dangerous_options(option_value):
                findings.append(
                    f"{path_name}:{index + 1}: service container options grant forbidden {label}"
                )
    return findings, covered


def violations(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{path}: read failure: {exc}"]

    lines = text.splitlines()
    findings: list[str] = []
    covered: set[int] = set()
    for index, line in enumerate(lines):
        match = CONTAINER_RE.match(line)
        if match:
            block_findings, block_covered = _container_block_findings(lines, path.name, index, match)
            findings.extend(block_findings)
            covered.update(block_covered)
        match = SERVICES_RE.match(line)
        if match:
            block_findings, block_covered = _services_block_findings(lines, path.name, index, match)
            findings.extend(block_findings)
            covered.update(block_covered)

    return findings


def main() -> int:
    workflows = workflow_files()
    if not workflows:
        print("No GitHub Actions workflows found.", file=sys.stderr)
        return 1
    findings: list[str] = []
    for path in workflows:
        findings.extend(violations(path))
    if findings:
        print("GitHub Actions container security violations detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print(f"Workflow container security gate passed for {len(workflows)} workflow files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
