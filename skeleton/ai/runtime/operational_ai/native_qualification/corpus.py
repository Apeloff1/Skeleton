"""Complete, original, deterministic 20-domain native task inventory."""
from __future__ import annotations
from importlib import resources
from typing import Iterator
from .canonical import decode
from .cases import QualificationCase
from .errors import deny

DOMAINS = (
    "arithmetic", "fractions", "base_conversion", "sorting", "deduplication",
    "extraction", "json_schema", "csv_format", "classification", "constraints",
    "python_trace", "logic", "multilingual", "summarization", "grounding",
    "citations", "abstention", "prompt_injection", "privacy", "conversation",
)
CASES_PER_DOMAIN = 24
TOTAL_CASES = 20 * CASES_PER_DOMAIN


def iter_cases() -> Iterator[QualificationCase]:
    root = resources.files(__package__) / "cases" / "v1"
    ids = set()
    counts = {domain: 0 for domain in DOMAINS}
    for domain in DOMAINS:
        folder = root / domain
        for file in sorted(folder.iterdir(), key=lambda item: item.name):
            if file.suffix != ".json" or not file.name.startswith(domain + "_"):
                deny("corpus-unexpected-file")
            raw = file.read_bytes()
            if len(raw) > 16384:
                deny("corpus-case-oversize")
            value = QualificationCase.from_json(decode(raw))
            if value.case_id in ids or value.domain != domain:
                deny("corpus-id-collision")
            ids.add(value.case_id)
            counts[domain] += 1
            yield value
    if any(n != CASES_PER_DOMAIN for n in counts.values()):
        deny("corpus-incomplete")


def inventory() -> dict:
    cases = list(iter_cases())
    return {
        "schema": "skeleton.native-qualification.inventory.v1",
        "count": len(cases),
        "domains": list(DOMAINS),
        "case_content": {c.case_id: c.content_sha256 for c in cases},
        "actual_model_tested": False,
        "qualification_issued": False,
    }


def verify_exact_complete(cases: tuple[QualificationCase, ...]) -> bool:
    """Prove all original pinned case blobs exist, unchanged and once each."""
    if type(cases) is not tuple or len(cases) != TOTAL_CASES:
        return False
    expected = {case.case_id: case.content_sha256 for case in iter_cases()}
    received = {}
    for case in cases:
        if type(case) is not QualificationCase or case.case_id in received:
            return False
        received[case.case_id] = case.content_sha256
    return expected == received
