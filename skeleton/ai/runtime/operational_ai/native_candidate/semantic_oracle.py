"""Independent deterministic ground truth for original training corpus examples.

Each domain is checked against a parser/calculator independent from the authored
answer. This is an *original-data correctness* gate, not a model-quality score.
"""
from __future__ import annotations
import json
import re

from .records import TrainingExample
from .errors import deny

_SEVERITIES = {"critical": "0", "high": "1", "medium": "2", "low": "3"}
_DIAG = {"healthy": "ready"}
_STATUS = {"queued": "pending", "running": "active", "paused": "held",
           "finished": "terminal", "cancelled": "terminal", "failed": "held"}
_UNITS = {"meter", "second", "byte", "kilogram", "ampere", "kelvin"}
_EXT = {"json":"structured_data","csv":"tabular_data","txt":"plain_text",
        "md":"markdown","py":"python_source","toml":"configuration"}
_EXPLAIN = {
    "hash": "A digest representing the bytes of content.",
    "token": "A unit the model uses to process text.",
    "snapshot": "A recorded state for restoration.",
    "revision": "A version number used to track changes.",
    "budget": "A maximum resource allowance.",
    "citation": "A reference connecting a claim to its source.",
}
_PHASES = {"intake":"verify","verify":"train","train":"evaluate",
           "evaluate":"publish_candidate","publish_candidate":"hold","hold":"hold"}


def _match(pattern: str, prompt: str) -> tuple[str, ...]:
    result = re.search(pattern, prompt)
    if result is None:
        deny("oracle-prompt-shape")
    return result.groups()


def expected_answer(item: TrainingExample) -> str:
    if type(item) is not TrainingExample:
        deny("oracle-source")
    domain, text = item.domain, item.prompt
    if domain == "number_ops":
        a, action, b = _match(r"Compute (\d+) (plus|minus|times) (\d+)", text) if "remainder" not in text else (None,None,None)
        if "remainder" in text:
            a, b = map(int, _match(r"remainder of (\d+) divided by (\d+)", text))
            return str(a % b)
        a, b = int(a), int(b)
        return str({"plus":lambda: a+b, "minus":lambda: a-b,
                    "times":lambda: a*b}[action]())
    if domain == "unit_words":
        quantity, unit = _match(r"Write (\d+) (meter|second|byte|kilogram|ampere|kelvin)s", text)
        if unit not in _UNITS:
            deny("oracle-unit")
        return f"{quantity} [{unit}]"
    if domain == "syntax":
        word, count = _match(r": ([A-Z]+) Service (\d+)\.", text)
        return word.lower() + "_service_" + count
    if domain == "json_repair":
        code, count = _match(r"string code (code_\d+) and integer count (\d+)", text)
        return json.dumps({"code":code,"count":int(count)},separators=(",",":"),sort_keys=True)
    if domain == "csv_columns":
        city, count = _match(r"one row ([A-Za-z]+),(\d+)", text)
        return f"place,count\n{city},{count}"
    if domain == "ids":
        count, = _match(r"task (\d+) alpha", text)
        return f"task_{count}_alpha"
    if domain == "file_types":
        ext, = _match(r"report_\d+\.(json|csv|txt|md|py|toml)", text)
        return _EXT[ext]
    if domain == "lists":
        numbers, = _match(r": ([0-9, ]+)\.", text)
        values = sorted(int(num.strip()) for num in numbers.split(","))
        return ", ".join(str(num) for num in values)
    if domain == "sets":
        sequence, = _match(r": ((?:[a-z0-9_, ]+))\.", text)
        return ", ".join(dict.fromkeys(value.strip() for value in sequence.split(",")))
    if domain == "inventory":
        a,b,c = map(int,_match(r"has (\d+) units, ships (\d+) and receives (\d+)",text))
        return str(a-b+c)
    if domain == "routing":
        result, = _match(r"target=(dispatch|queue|review|archive)", text)
        return result
    if domain == "priorities":
        severity, = _match(r"severity (critical|high|medium|low)", text)
        return _SEVERITIES[severity]
    if domain == "diagnostics":
        status, = _match(r"code ([a-z_]+)\.", text)
        return _DIAG.get(status,"blocked")
    if domain == "status":
        status, = _match(r"with status (queued|running|paused|finished|cancelled|failed)",text)
        return _STATUS[status]
    if domain == "limits":
        budget, spent = map(int,_match(r"holds (\d+) tokens and consumed (\d+)",text))
        return str(budget-spent)
    if domain == "ownership":
        owner, actor = _match(r"owner=(team_[a-d]) and caller=(team_[a-d])", text)
        return "yes" if owner == actor else "no"
    if domain == "permissions":
        capability, = _match(r"invoke (read|write|network|shell)", text)
        return "allow" if capability == "read" else "deny"
    if domain == "evidence":
        tag, = _match(r"records tag (blue|gold|green|violet)", text)
        return tag
    if domain == "provenance":
        author, = _match(r"original_author=(author_[abc])", text)
        return author
    if domain == "summaries":
        name,place = _match(r": ([A-Za-z]+) was deployed in ([A-Za-z]+)", text)
        return name + " in " + place
    if domain == "formatting":
        label,count = _match(r"label (\w+) and numeric identity (\d+)", text)
        return f"{label}:{count}"
    if domain == "categorization":
        subject, = _match(r"about a (invoice|deployment|parcel|contract)", text)
        return {"invoice":"finance", "deployment":"engineering",
                "parcel":"logistics", "contract":"human_resources"}[subject]
    if domain == "explanations":
        term, = _match(r"definition of (hash|token|snapshot|revision|budget|citation)", text)
        return _EXPLAIN[term]
    if domain == "workflow":
        phase, = _match(r"current phase=([a-z_]+)",text)
        if phase not in _PHASES:
            deny("oracle-phase")
        return _PHASES[phase]
    deny("oracle-domain")


def verify(item: TrainingExample) -> bool:
    if type(item) is not TrainingExample:
        deny("oracle-record")
    return expected_answer(item) == item.completion
