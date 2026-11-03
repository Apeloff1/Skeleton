"""Repeatable domain-interleaved schedule; no hidden random seeding."""
from __future__ import annotations
from collections import deque
from .catalog import DOMAINS
from .records import TrainingExample
from .strict import digest
from .errors import deny


def interleave(examples: tuple[TrainingExample, ...]) -> tuple[TrainingExample, ...]:
    if type(examples) is not tuple or len(examples) > 576:
        deny("curriculum-size")
    queues = {domain: deque() for domain in DOMAINS}
    for example in examples:
        if example.domain not in queues:
            deny("curriculum-domain")
        queues[example.domain].append(example)
    for domain in queues:
        queues[domain] = deque(sorted(queues[domain], key=lambda e: e.source_digest))
    result = []
    while any(queues.values()):
        for domain in DOMAINS:
            if queues[domain]:
                result.append(queues[domain].popleft())
    if len(result) != len(examples) or len({e.item_id for e in result}) != len(result):
        deny("curriculum-replay")
    return tuple(result)


def curriculum_digest(examples: tuple[TrainingExample, ...]) -> str:
    return digest([e.source_digest for e in interleave(examples)])
