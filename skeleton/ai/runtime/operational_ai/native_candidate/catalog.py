"""Versioned complete source catalog: 24 tasks per 24 independent domains."""
from __future__ import annotations
from importlib import resources
from .errors import deny
from .records import TrainingExample
from .strict import digest

DOMAINS = (
    "number_ops", "unit_words", "syntax", "json_repair", "csv_columns", "ids",
    "file_types", "lists", "sets", "inventory", "routing", "priorities",
    "diagnostics", "status", "limits", "ownership", "permissions", "evidence",
    "provenance", "summaries", "formatting", "categorization", "explanations",
    "workflow",
)
CASES_PER_DOMAIN = 24
TOTAL_EXAMPLES = 576


def iter_examples():
    root = resources.files(__package__) / "examples" / "v1"
    seen = set()
    for domain in DOMAINS:
        folder = root / domain
        count = 0
        for path in sorted(folder.iterdir(), key=lambda p: p.name):
            if path.suffix != ".json" or not path.name.startswith(domain + "_"):
                deny("catalog-unexpected-asset")
            raw = path.read_bytes()
            if len(raw) > 16384:
                deny("catalog-example-oversize")
            item = TrainingExample.parse(raw)
            if item.domain != domain or item.item_id != path.stem:
                deny("catalog-domain-id")
            if item.item_id in seen:
                deny("catalog-duplicate-id")
            seen.add(item.item_id)
            count += 1
            yield item
        if count != CASES_PER_DOMAIN:
            deny("catalog-incomplete")
    if len(seen) != TOTAL_EXAMPLES:
        deny("catalog-total")


def inventory() -> dict:
    examples = tuple(iter_examples())
    return {
        "schema": "skeleton.native-candidate.catalog.v1",
        "count": len(examples), "domains": list(DOMAINS),
        "source_hash": digest([e.record() for e in examples]),
        "entries": {e.item_id: e.source_digest for e in examples},
        "model_trained": False, "weights_created": False,
        "release_certified": False,
    }


def verify_exact(examples: tuple[TrainingExample, ...]) -> bool:
    if type(examples) is not tuple or len(examples) != TOTAL_EXAMPLES:
        return False
    expected = {e.item_id: e.source_digest for e in iter_examples()}
    actual = {}
    for entry in examples:
        if type(entry) is not TrainingExample or entry.item_id in actual:
            return False
        actual[entry.item_id] = entry.source_digest
    return expected == actual
