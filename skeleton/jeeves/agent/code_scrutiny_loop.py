"""Host-controlled iterative source review with indexed findings and receipts.

No shell execution, network access, or autonomous source mutation is performed
here. Language-specific analyzers and authorized repair gateways are injected by
the host; a missing checker is *not* evidence that a source file is valid.
Each pass rechecks every in-scope file, and every correction is reverified.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Callable, Mapping, Sequence

from .types import stable_fingerprint

_FIND_TERMS = re.compile(r"(?:error|failure|exception|syntax|lint|type|import|stub|traceback)", re.I)
_FIXME = re.compile(r"^(?:raise NotImplementedError\b|TODO\s*:|FIXME\s*:)", re.I)
_CONFLICT = re.compile(r"^(?:<<<<<<< |=======\s*$|>>>>>>> )")
_PYTHON = {".py", ".pyi"}
_JSON = {".json"}
_SUPPORTED_HOOKS = {".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".cs", ".gd", ".java", ".kt", ".sh"}


@dataclass(frozen=True, slots=True)
class CodeFinding:
    path: str
    line: int
    category: str
    code: str
    message: str
    checker: str

    def __post_init__(self) -> None:
        if not self.path or self.path.startswith("/") or ".." in PurePosixPath(self.path).parts:
            raise ValueError("unsafe finding path")
        if type(self.line) is not int or self.line < 1:
            raise ValueError("finding line must be positive")
        if not all(isinstance(x, str) and x.strip() for x in (
            self.category, self.code, self.message, self.checker
        )):
            raise ValueError("finding fields must be nonempty")

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "path": self.path, "line": self.line, "category": self.category,
            "code": self.code, "message": self.message, "checker": self.checker,
        })


@dataclass(frozen=True, slots=True)
class ScrutinyPolicy:
    maximum_passes: int = 48
    stability_passes: int = 2
    maximum_files: int = 512
    maximum_chars_per_file: int = 250_000
    maximum_findings: int = 10_000

    def __post_init__(self) -> None:
        values = (self.maximum_passes, self.stability_passes, self.maximum_files,
                  self.maximum_chars_per_file, self.maximum_findings)
        if any(type(n) is not int or n <= 0 for n in values):
            raise ValueError("scrutiny policy requires positive integer limits")
        if self.maximum_passes < self.stability_passes:
            raise ValueError("scrutiny cannot establish stability within pass budget")


@dataclass(frozen=True, slots=True)
class ScrutinyReceipt:
    pass_number: int
    serial: str
    source_root: str
    findings_root: str
    action: str
    previous: str
    digest: str

    @classmethod
    def create(cls, pass_number: int, source_root: str, findings_root: str,
               action: str, previous: str) -> "ScrutinyReceipt":
        serial = f"JVC-{pass_number:08X}-P{pass_number:08d}"
        digest = stable_fingerprint({
            "pass": pass_number, "serial": serial, "source": source_root,
            "findings": findings_root, "action": action, "previous": previous,
        })
        return cls(pass_number, serial, source_root, findings_root, action, previous, digest)


@dataclass(frozen=True, slots=True)
class ScrutinyOutcome:
    status: str
    files: Mapping[str, str]
    findings: tuple[CodeFinding, ...]
    receipts: tuple[ScrutinyReceipt, ...]
    corrections: int
    stable_passes: int
    errors_searched: tuple[str, ...]
    reason: str

    @property
    def success(self) -> bool:
        return self.status == "verified_clean"

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "status": self.status,
            "files": stable_fingerprint(dict(self.files)),
            "findings": [finding.fingerprint for finding in self.findings],
            "receipts": [item.digest for item in self.receipts],
            "corrections": self.corrections,
            "stable_passes": self.stable_passes,
            "queries": self.errors_searched,
            "reason": self.reason,
        })


# Host-provided adapters must return structured evidence. They are not model
# instructions and may not execute repairs without independent authorization.
Checker = Callable[[Mapping[str, str]], Sequence[CodeFinding]]
Discovery = Callable[[Mapping[str, str], tuple[str, ...], int], Mapping[str, str]]
Repair = Callable[[Mapping[str, str], tuple[CodeFinding, ...], int], Mapping[str, str]]


def _validated_files(files: Mapping[str, str], policy: ScrutinyPolicy) -> dict[str, str]:
    if len(files) > policy.maximum_files:
        raise ValueError("code scrutiny file cap exceeded")
    result: dict[str, str] = {}
    for path, content in sorted(files.items()):
        if not isinstance(path, str) or not path or path.startswith("/"):
            raise ValueError("invalid source path")
        normalized = PurePosixPath(path)
        if ".." in normalized.parts or "\\" in path or str(normalized) != path:
            raise ValueError("unsafe source path")
        if not isinstance(content, str) or len(content) > policy.maximum_chars_per_file:
            raise ValueError("invalid or oversized source")
        result[path] = content
    return result


def _builtin_checks(files: Mapping[str, str], *, external_checker: bool) -> tuple[CodeFinding, ...]:
    findings: list[CodeFinding] = []
    for path, source in files.items():
        extension = PurePosixPath(path).suffix.lower()
        if extension in _PYTHON:
            try:
                # Compiling without executing also rejects top-level return,
                # nonlocal misuse and other errors AST parsing can admit.
                compile(source, path, "exec", dont_inherit=True)
            except (SyntaxError, ValueError) as exc:
                findings.append(CodeFinding(
                    path, max(1, getattr(exc, "lineno", None) or 1), "syntax", "PY_SYNTAX",
                    str(getattr(exc, "msg", str(exc)))[:256], "python-compiler",
                ))
        elif extension in _JSON:
            try:
                json.loads(source)
            except json.JSONDecodeError as exc:
                findings.append(CodeFinding(
                    path, max(1, exc.lineno), "syntax", "JSON_SYNTAX",
                    str(exc.msg)[:256], "json-decoder",
                ))
        elif not external_checker:
            findings.append(CodeFinding(path, 1, "coverage", "CHECKER_REQUIRED",
                                        f"No registered checker for {extension or 'extensionless'} source",
                                        "language-coverage"))
        for line_number, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if _CONFLICT.match(stripped):
                findings.append(CodeFinding(path, line_number, "review", "MERGE_CONFLICT",
                                            "Unresolved merge conflict marker", "source-review"))
            if extension in _PYTHON and _FIXME.match(stripped):
                findings.append(CodeFinding(path, line_number, "review", "UNFINISHED_CODE",
                                            "Explicit unimplemented source marker", "source-review"))
    return tuple(findings)


def _check_adapters(items: Sequence[CodeFinding], files: Mapping[str, str], name: str) -> tuple[CodeFinding, ...]:
    findings = tuple(items)
    if any(not isinstance(item, CodeFinding) or item.path not in files for item in findings):
        raise ValueError(f"{name} produced an ungrounded finding")
    return findings


def verify_scrutiny_receipts(outcome: ScrutinyOutcome) -> None:
    previous = "0" * 64
    for i, item in enumerate(outcome.receipts, 1):
        expected = ScrutinyReceipt.create(i, item.source_root, item.findings_root,
                                          item.action, previous)
        if expected != item:
            raise ValueError("code scrutiny receipt chain or sequence was tampered")
        previous = item.digest
    if outcome.success:
        if outcome.findings or outcome.stable_passes < 2 or not outcome.receipts:
            raise ValueError("premature clean status in code scrutiny")


class CodeScrutinyLoop:
    """Search, audit, propose repair, rescan until stable or fail explicitly."""

    def __init__(self, policy: ScrutinyPolicy | None = None) -> None:
        self.policy = policy or ScrutinyPolicy()

    def run(
        self,
        files: Mapping[str, str],
        *,
        lint: Checker | None = None,
        code_review: Checker | None = None,
        error_search: Checker | None = None,
        discover: Discovery | None = None,
        repair: Repair | None = None,
        authorized: bool = False,
        seed_terms: Sequence[str] = ("error", "syntax", "lint", "import", "type"),
    ) -> ScrutinyOutcome:
        sources = _validated_files(files, self.policy)
        if not sources:
            raise ValueError("code scrutiny needs at least one source")
        terms = list(dict.fromkeys(str(q)[:100] for q in seed_terms if str(q).strip()))
        receipts: list[ScrutinyReceipt] = []
        previous = "0" * 64
        previous_root: str | None = None
        stable = 0
        corrections = 0
        last_findings: tuple[CodeFinding, ...] = ()

        def result(status: str, reason: str) -> ScrutinyOutcome:
            answer = ScrutinyOutcome(status, dict(sources), last_findings,
                                     tuple(receipts), corrections, stable,
                                     tuple(terms), reason)
            verify_scrutiny_receipts(answer)
            return answer

        for index in range(1, self.policy.maximum_passes + 1):
            if discover is not None:
                # Discovery must disclose what was actually searched. It cannot
                # silently remove earlier sources to create a false clean pass.
                additional = _validated_files(discover(dict(sources), tuple(terms), index), self.policy)
                for path, content in additional.items():
                    if path in sources and sources[path] != content:
                        raise ValueError("discovery changed a previously reviewed source")
                sources.update(additional)
                sources = _validated_files(sources, self.policy)

            checks: list[CodeFinding] = list(_builtin_checks(
                sources, external_checker=lint is not None
            ))
            for name, callback in (
                ("lint", lint), ("code_review", code_review), ("error_search", error_search),
            ):
                if callback is not None:
                    checks.extend(_check_adapters(callback(dict(sources)), sources, name))
            # Multiple tools may report the same problem; deduplicate by semantic key.
            unique = {item.fingerprint: item for item in checks}
            last_findings = tuple(sorted(unique.values(), key=lambda x: (
                x.path, x.line, x.category, x.code, x.checker
            )))
            if len(last_findings) > self.policy.maximum_findings:
                raise ValueError("too many code scrutiny findings")
            root = stable_fingerprint(dict(sources))
            findings_root = stable_fingerprint([item.fingerprint for item in last_findings])
            action = "clean_review" if not last_findings else "errors_found"
            receipt = ScrutinyReceipt.create(index, root, findings_root, action, previous)
            receipts.append(receipt)
            previous = receipt.digest

            if not last_findings:
                stable = stable + 1 if root == previous_root else 1
                previous_root = root
                if stable >= self.policy.stability_passes:
                    return result("verified_clean", "Two consecutive stable scrutiny passes")
                continue

            stable = 0
            previous_root = None
            for finding in last_findings:
                query = f"{finding.category}:{finding.code}:{PurePosixPath(finding.path).name}"
                if _FIND_TERMS.search(query) and query not in terms:
                    terms.append(query[:160])
            if repair is None:
                return result("blocked_no_repair", "No authorized correction adapter is available")
            if not authorized:
                return result("blocked_not_authorized", "Source correction was not authorized")
            repaired = _validated_files(repair(dict(sources), last_findings, index), self.policy)
            if set(repaired) != set(sources):
                raise ValueError("repair adapter cannot add or drop reviewed files")
            if repaired == sources:
                return result("blocked_no_progress", "Correction did not change any source")
            sources = repaired
            corrections += 1

        return result("budget_exhausted", "Scrutiny pass budget exhausted; unresolved state requires continuation")
