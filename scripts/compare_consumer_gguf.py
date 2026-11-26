"""Offline, exact-output consumer GGUF comparator; no deployment promotion.

Uses the existing digest-bound native qualification owner. Elapsed times are
end-to-end wall times (including artifact verification and process startup),
not decode tokens/second, peak memory, or independent benchmark evidence.
No network, model downloads, prompt logs or generated-code execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from skeleton.ai.runtime.inference.deployment import (
    LocalModelDeployment,
    LocalModelDeploymentError,
    QUALIFICATION_SCHEMA,
    qualify_local_model_deployment_sync,
)

_HEX = re.compile(r"[0-9a-f]{64}")
_LABEL = re.compile(r"[a-zA-Z0-9_-]{1,40}")
_MAX_ATTEMPTS = 144


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Task:
    name: str
    category: str
    prompt: str
    exact: str
    max_tokens: int = 32


# Public diagnostic, not a held-out quality or general intelligence benchmark.
# Exact bytes intentionally distinguish formatting reliability from semantic correctness.
_TASKS = (
    Task("arithmetic", "reasoning", "Return only the integer 17 * 19 - 11.", "312"),
    Task("modular", "reasoning", "Return only the remainder of 137 divided by 12.", "5"),
    Task("ordering", "reasoning", "A is before B; C is after B. Return the order as three uppercase letters without separators.", "ABC"),
    Task("logic", "reasoning", "Every dax is a mip. No mip is a zop. Can a dax be a zop? Output only YES or NO.", "NO"),
    Task("python", "code", "In Python, what is len(set([1, 1, 2, 3, 3]))? Output only the integer.", "3"),
    Task("python_slice", "code", "In Python, what is list(range(8))[1:7:2]? Output exactly the Python list, including spaces.", "[1, 3, 5]"),
    Task("binary", "code", "Convert binary 101101 to decimal. Output only the integer.", "45"),
    Task("json", "format", 'Output precisely this compact JSON object and nothing else: {"ready":true}', '{"ready":true}'),
    Task("case", "format", "Reverse the five letters AbCdE without changing their case. Output only the result.", "EdCbA"),
    Task("extract", "grounding", "Record: version=12; owner=Rhea; status=held. Output only the owner.", "Rhea"),
    Task("unknown", "grounding", "Record: title=Moon; owner=Lee. The date is absent. What is the date? Output UNKNOWN if absent, otherwise the date.", "UNKNOWN"),
    Task("revision", "grounding", "Old record: color=red. Replacement record: color=blue. Output only the current color.", "blue"),
)


@dataclass(frozen=True)
class Profile:
    label: str
    manifest: Path
    manifest_sha256: str
    model_sha256: str
    executable_sha256: str
    model_id: str
    manifest_file_sha256: str

    def __post_init__(self):
        if not isinstance(self.label, str) or not _LABEL.fullmatch(self.label):
            raise ValueError("invalid profile label")
        for value in (self.manifest_sha256, self.model_sha256, self.executable_sha256, self.manifest_file_sha256):
            if not isinstance(value, str) or not _HEX.fullmatch(value):
                raise ValueError("profile requires exact SHA-256 identities")
        if not isinstance(self.model_id, str) or not self.model_id or len(self.model_id) > 1024:
            raise ValueError("invalid model identity")

    @classmethod
    def load(cls, label: str, manifest: Path) -> Profile:
        manifest = manifest.expanduser().resolve(strict=True)
        with manifest.open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        if not 1 <= len(raw) <= 1024 * 1024:
            raise ValueError("manifest file exceeds bounds")
        file_digest = hashlib.sha256(raw).hexdigest()
        deployment = LocalModelDeployment.load(manifest, expected_sha256=file_digest)
        if deployment.temperature != 0:
            raise ValueError("matched diagnostic requires greedy temperature zero")
        if deployment.timeout_seconds > 300:
            raise ValueError("diagnostic profile timeout must be at most 300 seconds")
        return cls(label, deployment.manifest_path, deployment.manifest_digest,
                   deployment.execution_model_sha256, deployment.executable_sha256, deployment.model_id, file_digest)

    def public(self) -> dict:
        return dict(label=self.label, manifest_sha256=self.manifest_sha256,
                    model_sha256=self.model_sha256, executable_sha256=self.executable_sha256,
                    model_id_sha256=_text_digest(self.model_id), manifest_file_sha256=self.manifest_file_sha256)


def _receipt(profile: Profile, task: Task, receipt: object) -> str:
    if not isinstance(receipt, dict):
        raise ValueError("invalid native receipt")
    expected = {
        "schema_version": QUALIFICATION_SCHEMA, "status": "qualified",
        "provider": "local", "manifest_sha256": profile.manifest_sha256,
        "model_sha256": profile.model_sha256, "executable_sha256": profile.executable_sha256,
        "model_id": profile.model_id, "prompt_sha256": _text_digest(task.prompt),
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError("native receipt identity drift")
    if receipt.get("network_required") is not False or receipt.get("hosted_provider_credentials_required") is not False:
        raise ValueError("native receipt violates local-only contract")
    for key in ("receipt_digest", "output_sha256"):
        if not isinstance(receipt.get(key), str) or not _HEX.fullmatch(receipt[key]):
            raise ValueError("invalid native receipt digest")
    payload = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    if _digest(payload) != receipt["receipt_digest"]:
        raise ValueError("native receipt digest mismatch")
    return receipt["output_sha256"]


def _summary(rows: list[dict]) -> dict:
    completed = [r for r in rows if r["status"] in {"exact", "different"}]
    # Keep failed attempts in the denominator; do not hide timeouts.
    latencies = sorted(r["elapsed_seconds"] for r in completed)
    categories = {}
    for row in rows:
        group = categories.setdefault(row["category"], {"exact": 0, "attempts": 0})
        group["attempts"] += 1
        group["exact"] += row["status"] == "exact"
    return {
        "attempts": len(rows), "native_completed": len(completed),
        "exact": sum(r["status"] == "exact" for r in rows),
        "failed": len(rows) - len(completed),
        "categories": categories,
        "median_completed_wall_seconds": statistics.median(latencies) if latencies else None,
        "p95_completed_wall_seconds": latencies[math.ceil(len(latencies)*.95)-1] if latencies else None,
    }


def compare(
    profiles: Sequence[Profile], *, repeats: int = 1, deadline_seconds: int = 3600,
    qualify: Callable = qualify_local_model_deployment_sync,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    if not 2 <= len(profiles) <= 4 or len({p.label for p in profiles}) != len(profiles):
        raise ValueError("provide 2–4 distinct profile labels")
    if len({p.manifest_sha256 for p in profiles}) != len(profiles):
        raise ValueError("duplicate manifests do not constitute independent profiles")
    if type(repeats) is not int or not 1 <= repeats <= 3:
        raise ValueError("repeats must be 1–3")
    if len(profiles) * len(_TASKS) * repeats > _MAX_ATTEMPTS:
        raise ValueError("attempt limit exceeded")
    if type(deadline_seconds) is not int or not 1 <= deadline_seconds <= 14400:
        raise ValueError("campaign admission deadline outside bounds")
    start = clock()
    rows = []
    holds = set()
    for repeat in range(repeats):
        tasks = _TASKS if repeat % 2 == 0 else tuple(reversed(_TASKS))
        for task_index, task in enumerate(tasks):
            # Rotate execution position each task to reduce fixed ordering bias.
            offset = (repeat + task_index) % len(profiles)
            ordered = list(profiles[offset:]) + list(profiles[:offset])
            for profile in ordered:
                row = dict(profile=profile.label, task=task.name, category=task.category,
                           repeat=repeat, elapsed_seconds=None, receipt_sha256=None)
                if profile.label in holds:
                    row["status"] = "held_identity"
                elif clock() - start >= deadline_seconds:
                    row["status"] = "not_started_deadline"
                else:
                    began = clock()
                    try:
                        receipt = qualify(profile.manifest, prompt=task.prompt,
                                          max_output_tokens=task.max_tokens,
                                          expected_manifest_sha256=profile.manifest_file_sha256)
                    except (LocalModelDeploymentError, OSError, TimeoutError):
                        row["status"] = "execution_failed"
                    else:
                        try:
                            output = _receipt(profile, task, receipt)
                        except (ValueError, TypeError):
                            holds.add(profile.label)
                            row["status"] = "identity_rejected"
                        else:
                            row["status"] = "exact" if output == _text_digest(task.exact) else "different"
                            row["receipt_sha256"] = receipt["receipt_digest"]
                    row["elapsed_seconds"] = round(max(0.0, clock() - began), 6)
                rows.append(row)
    summaries = {profile.label: _summary([r for r in rows if r["profile"] == profile.label])
                 for profile in profiles}
    reference = profiles[0].label
    paired = {}
    indexed = {(r["profile"], r["task"], r["repeat"]): r for r in rows}
    for profile in profiles[1:]:
        wins = losses = ties = joint_exact = unmatched = 0
        ratios = []
        for task in _TASKS:
            for repeat in range(repeats):
                baseline = indexed[reference, task.name, repeat]
                contender = indexed[profile.label, task.name, repeat]
                if not all(row["status"] in {"exact", "different"} for row in (baseline, contender)):
                    unmatched += 1
                    continue
                a, b = baseline["status"] == "exact", contender["status"] == "exact"
                wins += b and not a
                losses += a and not b
                ties += a == b
                if a and b:
                    joint_exact += 1
                    if baseline["elapsed_seconds"] > 0:
                        ratios.append(contender["elapsed_seconds"] / baseline["elapsed_seconds"])
        paired[profile.label] = dict(exact_wins=wins, exact_losses=losses, exact_ties=ties,
                                    jointly_exact=joint_exact, unmatched_attempt_pairs=unmatched,
                                    median_wall_ratio_on_joint_exact=statistics.median(ratios) if ratios else None)
    report = {
        "schema": "skeleton.gguf.matched-diagnostic.v1",
        "status": "advisory_only", "reference": reference,
        "corpus_sha256": _digest([vars(task) for task in _TASKS]),
        "scorer": "exact_utf8_sha256_v1",
        "scorer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "profiles": [p.public() for p in profiles],
        "repeats": repeats, "deadline_seconds": deadline_seconds,
        "planned_attempts": len(profiles)*len(_TASKS)*repeats,
        "identity_holds": sorted(holds), "summaries": summaries, "paired": paired, "rows": rows,
        "limits": ["public diagnostic", "no semantic partial credit", "wall time includes custody and launch",
                   "deadline stops new admission only", "no physical memory or quality certification"],
    }
    report["report_sha256"] = _digest(report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", required=True, metavar="LABEL=MANIFEST")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--deadline-seconds", type=int, default=3600)
    args = parser.parse_args(argv)
    if not 2 <= len(args.profile) <= 4:
        parser.error("2–4 profiles required")
    try:
        profiles = [Profile.load(label, Path(path)) for label, path in
                    (entry.split("=", 1) for entry in args.profile)]
        report = compare(profiles, repeats=args.repeats, deadline_seconds=args.deadline_seconds)
    except (ValueError, OSError, LocalModelDeploymentError):
        parser.exit(2, "GGUF comparison rejected: invalid or unavailable local profile\n")
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return 0 if all(row["status"] in {"exact", "different"} for row in report["rows"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
