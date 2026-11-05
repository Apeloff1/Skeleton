"""Original, rights-bound, source-identified candidate training examples.

Examples are source code/data, never model-generated authority or a runtime
checkpoint. No network, hidden third-party books, or gameplay content.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .strict import digest, identity, string
from .errors import deny

SCHEMA = "skeleton.native-candidate.example.v1"
LICENSE = "skeleton_original"
SCOPE = "offline_native_candidate_training"
RIGHTS = "allowed"
PROVENANCE = "original_synthetic_authored"


@dataclass(frozen=True, slots=True)
class TrainingExample:
    item_id: str
    domain: str
    prompt: str
    completion: str
    group_id: str
    rights_status: str = RIGHTS
    license_id: str = LICENSE
    training_scope: str = SCOPE
    provenance: str = PROVENANCE

    def __post_init__(self) -> None:
        for name in ("item_id", "domain", "group_id", "license_id", "training_scope", "provenance"):
            identity(getattr(self, name), name)
        string(self.prompt, "prompt", 2048)
        string(self.completion, "completion", 2048)
        if not self.prompt.strip() or not self.completion.strip():
            deny("training-empty")
        if self.rights_status != RIGHTS or self.license_id != LICENSE:
            deny("training-rights")
        if self.training_scope != SCOPE or self.provenance != PROVENANCE:
            deny("training-purpose")
        if "\x00" in self.prompt + self.completion:
            deny("training-control")

    @classmethod
    def parse(cls, raw: bytes) -> "TrainingExample":
        from .strict import decode
        value = decode(raw)
        fields = {
            "schema", "id", "domain", "prompt", "completion", "group_id",
            "rights_status", "license_id", "training_scope", "provenance",
        }
        if type(value) is not dict or set(value) != fields or value["schema"] != SCHEMA:
            deny("training-example-schema")
        return cls(
            value["id"], value["domain"], value["prompt"], value["completion"],
            value["group_id"], value["rights_status"], value["license_id"],
            value["training_scope"], value["provenance"],
        )

    def record(self) -> dict:
        return {
            "schema": SCHEMA, "id": self.item_id, "domain": self.domain,
            "prompt": self.prompt, "completion": self.completion,
            "group_id": self.group_id, "rights_status": self.rights_status,
            "license_id": self.license_id, "training_scope": self.training_scope,
            "provenance": self.provenance,
        }

    @property
    def source_digest(self) -> str:
        return digest(self.record())

    def render(self) -> str:
        # This line is for the existing native next-token trainer. The
        # training model's actual tokenizer must independently admit it.
        line = "Instruction: " + self.prompt.strip() + "\nResponse: " + self.completion.strip()
        if len(line.encode("utf-8")) > 4096:
            deny("training-line-budget")
        return line
