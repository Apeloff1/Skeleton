"""Fail-closed policy for GitHub Actions job/service container images and options."""
from __future__ import annotations

from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
SHA256_IMAGE_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-fA-F]{64}$")
KEY_RE = re.compile(
    r"^(?P<indent>\s*)(?:-\s*)?[\"']?(?P<key>[A-Za-z0-9_.-]+)[\"']?\s*:\s*(?P<value>.*)$"
)
FLOW_IMAGE_RE = re.compile(
    r"(?:^|[{,]\s*)[\"']?image[\"']?\s*:\s*(?P<value>[^,}]+)"
)
FLOW_OPTIONS_RE = re.compile(
    r"(?:^|[{,]\s*)[\"']?options[\"']?\s*:\s*(?P<value>[^,}]+)"
)
BLOCK_SCALARS = {"|", "|-", "|+", ">", ">-", ">+"}

FORBIDDEN_OPTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("privileged container mode", re.compile(r"(?:^|\s)--privileged(?:\s|$|=)", re.I)),
    ("host network namespace", re.compile(r"(?:^|\s)--network(?:=|\s+)host(?:\s|$)", re.I)),
    ("host PID namespace", re.compile(r"(?:^|\s)--pid(?:=|\s+)host(?:\s|$)", re.I)),
    ("host IPC namespace", re.compile(r"(?:^|\s)--ipc(?:=|\s+)host(?:\s|$)", re.I)),
    ("host user namespace", re.compile(r"(?:^|\s)--userns(?:=|\s+)host(?:\s|$)", re.I)),
    ("device passthrough", re.compile(r"(?:^|\s)--device(?:=|\s+)", re.I)),
    ("Linux capability elevation", re.compile(r"(?:^|\s)--cap-add(?:=|\s+)", re.I)),
    (
        "unconfined security profile",
        re.compile(r"(?:^|\s)--security-opt(?:=|\s+)[^\s]*(?:apparmor|seccomp)[=:]unconfined", re.I),
    ),
    (
        "Docker daemon socket mount",
        re.compile(
            r"(?:^|\s)(?:-v|--volume)(?:=|\s+)[^\s]*(?:/var/run/docker\.sock|/run/docker\.sock)(?::|\s|$)",
            re.I,
        ),
    ),
)


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])


def _strip_scalar(value: str) -> str:
    value = value.split("#", 1)[0].strip().rstrip(",}").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def _image_finding(path_name: str, number: int, value: str) -> str | None:
    reference = _strip_scalar(value)
    if SHA256_IMAGE_RE.fullmatch(reference):
        return None
    return (
        f"{path_name}:{number}: GitHub Actions job/service container image must be "
        f"pinned to an immutable sha256 digest: {reference or '<empty>'}"
    )


def _option_findings(path_name: str, number: int, value: str) -> list[str]:
    option_text = _strip_scalar(value)
    if option_text in BLOCK_SCALARS:
        return [
            f"{path_name}:{number}: block-scalar GitHub Actions container options are forbidden; "
            "use a single-line literal so the security gate can inspect every option"
        ]

    findings: list[str] = []
    for label, pattern in FORBIDDEN_OPTION_PATTERNS:
        if pattern.search(option_text):
            findings.append(
                f"{path_name}:{number}: forbidden GitHub Actions container option ({label})"
            )
    return findings


def _flow_findings(path_name: str, number: int, value: str) -> list[str]:
    findings: list[str] = []
    for flow_match in FLOW_IMAGE_RE.finditer(value):
        finding = _image_finding(path_name, number, flow_match.group("value"))
        if finding:
            findings.append(finding)
    for flow_match in FLOW_OPTIONS_RE.finditer(value):
        findings.extend(_option_findings(path_name, number, flow_match.group("value")))
    return findings


def violations(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{path}: read failure: {exc}"]

    findings: list[str] = []
    stack: list[tuple[int, str]] = []

    for number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        match = KEY_RE.match(raw_line)
        if not match:
            continue

        indent = len(match.group("indent"))
        key = match.group("key")
        value = match.group("value").strip()

        while stack and stack[-1][0] >= indent:
            stack.pop()
        ancestors = [ancestor for _level, ancestor in stack]
        in_jobs = "jobs" in ancestors or key == "jobs"
        in_container_scope = "container" in ancestors or "services" in ancestors

        if in_jobs and key == "container" and value:
            if value.startswith("{"):
                findings.extend(_flow_findings(path.name, number, value))
            else:
                finding = _image_finding(path.name, number, value)
                if finding:
                    findings.append(finding)

        if in_jobs and key == "services" and value.startswith("{"):
            findings.extend(_flow_findings(path.name, number, value))

        if in_jobs and key == "image" and in_container_scope:
            finding = _image_finding(path.name, number, value)
            if finding:
                findings.append(finding)

        if in_jobs and key == "options" and in_container_scope:
            findings.extend(_option_findings(path.name, number, value))

        # Mapping nodes establish context for following indented keys. Block scalar
        # values do not contain nested YAML mappings and therefore are not pushed.
        if not value and key not in {"run"}:
            stack.append((indent, key))

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
