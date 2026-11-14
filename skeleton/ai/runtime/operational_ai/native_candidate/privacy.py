"""Prevent raw source prompts and private training artifacts in report exports."""
from __future__ import annotations

from .errors import deny

BLOCKED = frozenset({
    "prompt", "completion", "private_path", "checkpoint_json",
    "raw_training_text", "memory_content", "model_output", "bearer", "secret",
    "api_key", "token", "access_token",
})


def inspect_public_record(value: object, *, maximum_nodes: int = 100000) -> dict:
    count = 0
    forbidden = []
    def walk(node: object, path: str) -> None:
        nonlocal count
        count += 1
        if count > maximum_nodes:
            deny("privacy-budget")
        if type(node) is dict:
            for name, item in node.items():
                if type(name) is not str:
                    deny("privacy-key")
                if name.lower() in BLOCKED:
                    forbidden.append(path + "." + name)
                walk(item, path + "." + name)
        elif type(node) in (tuple, list):
            for index, item in enumerate(node):
                walk(item, path + "[" + str(index) + "]")
        elif node is not None and type(node) not in (str, int, float, bool):
            deny("privacy-type")
    walk(value, "root")
    return {"publishable": not forbidden, "blocked": tuple(forbidden),
            "nodes": count}
