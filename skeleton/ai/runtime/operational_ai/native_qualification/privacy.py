"""Never publish model text or prompts in routine qualification artifacts."""
from __future__ import annotations
from .errors import deny

BLOCKED_FIELDS = frozenset({
    "question", "prompt", "model_output", "raw_output", "raw_response",
    "system", "system_prompt", "evidence_bytes", "memory_text", "secret",
    "private_path", "bearer", "authorization", "api_key",
})
MAX_REPORT_NODES = 50000


def inspect_public_fields(report: object) -> dict:
    count = 0
    flagged = []

    def visit(value: object, path: str) -> None:
        nonlocal count
        count += 1
        if count > MAX_REPORT_NODES:
            deny("privacy-report-size")
        if type(value) is dict:
            for key, item in value.items():
                if type(key) is not str:
                    deny("privacy-key")
                if key.lower() in BLOCKED_FIELDS:
                    flagged.append(path + "." + key)
                visit(item, path + "." + key)
        elif type(value) is list:
            for index, item in enumerate(value):
                visit(item, path + "[" + str(index) + "]")
        elif value is not None and type(value) not in (bool, int, float, str):
            deny("privacy-type")
    visit(report, "report")
    return {"blocked_fields": tuple(flagged), "publishable": not flagged, "nodes": count}
