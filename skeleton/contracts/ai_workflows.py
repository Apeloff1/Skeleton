"""Bounded workflow starters for explicit draft configuration.

Templates contain form budgets and presentation metadata. They execute nothing,
grant no authority and do not establish that a provider or studio is available.
The existing command owners still validate every submitted request.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

WORKFLOW_CATALOG_SCHEMA = "skeleton.ai.workflow_catalog.v1"
WORKFLOW_TEMPLATE_SCHEMA = "skeleton.ai.workflow_template.v1"
WORKFLOW_CATALOG_VERSION = 1
MAX_WORKFLOW_TEMPLATES = 16
MAX_WORKFLOW_CATALOG_BYTES = 64 * 1024

WorkflowSurface = Literal["chat", "studio", "crawler"]
WorkflowSetting = bool | int | str
_TEMPLATE_ID = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,3}\Z")


class WorkflowTemplateError(ValueError):
    """A workflow draft or template exceeds its declared static contract."""


@dataclass(frozen=True, slots=True)
class _SettingRule:
    kind: Literal["integer", "boolean", "choice"]
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] = ()

    def validate(self, name: str, value: object) -> WorkflowSetting:
        if self.kind == "boolean":
            if type(value) is not bool:
                raise WorkflowTemplateError(f"{name} must be a boolean")
        elif self.kind == "integer":
            if type(value) is not int or not self.minimum <= value <= self.maximum:
                raise WorkflowTemplateError(f"{name} exceeds its integer bounds")
        elif type(value) is not str or value not in self.choices:
            raise WorkflowTemplateError(f"{name} is not a supported draft choice")
        return value


# These are draft-only limits. A selected model or current owner may impose
# smaller limits. The settings deliberately exclude every execution/consent key.
_SETTING_RULES = MappingProxyType(
    {
        "chat": MappingProxyType(
            {
                "max_tokens": _SettingRule("integer", 1, 8192),
                "review_response": _SettingRule("boolean"),
            }
        ),
        "studio": MappingProxyType(
            {
                "max_steps": _SettingRule("integer", 1, 16),
                "max_model_calls": _SettingRule("integer", 1, 16),
                "max_jobs": _SettingRule("integer", 0, 8),
                "max_output_tokens": _SettingRule("integer", 256, 4096),
                "authorization_seconds": _SettingRule("integer", 60, 3600),
                "completion_mode": _SettingRule("choice", choices=("native", "original")),
            }
        ),
        "crawler": MappingProxyType(
            {
                "max_requests": _SettingRule("integer", 1, 128),
                "max_documents": _SettingRule("integer", 1, 64),
                "max_bytes": _SettingRule("integer", 1024, 32 * 1024 * 1024),
                "max_depth": _SettingRule("integer", 0, 3),
            }
        ),
    }
)


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise WorkflowTemplateError("workflow metadata must be finite UTF-8 JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _text(value: object, name: str, maximum: int) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise WorkflowTemplateError(f"{name} must be bounded normalized text")
    return value


def validate_workflow_settings(
    surface: WorkflowSurface, settings: Mapping[str, object]
) -> dict[str, WorkflowSetting]:
    """Return a new settings value after rejecting unknown or incomplete fields.

    This validates a complete draft template. It does not grant permission to
    submit it or replace the actual provider, project or crawler checks.
    """
    if type(surface) is not str or surface not in _SETTING_RULES:
        raise WorkflowTemplateError("unknown workflow surface")
    rules = _SETTING_RULES[surface]
    if not isinstance(settings, Mapping) or set(settings) != set(rules):
        raise WorkflowTemplateError("workflow settings require the exact declared fields")
    return {name: rule.validate(name, settings[name]) for name, rule in rules.items()}


@dataclass(frozen=True, slots=True)
class WorkflowTemplate:
    """Immutable presentation and budget metadata, with no runtime state."""

    template_id: str
    surface: WorkflowSurface
    title: str
    description: str
    settings: tuple[tuple[str, WorkflowSetting], ...]
    requirements: tuple[str, ...]
    revision: int = 1

    def __post_init__(self) -> None:
        identifier = _text(self.template_id, "template_id", 96)
        if _TEMPLATE_ID.fullmatch(identifier) is None or not identifier.startswith(self.surface + "."):
            raise WorkflowTemplateError("template identity must name its workflow surface")
        if type(self.revision) is not int or not 1 <= self.revision <= 1_000_000:
            raise WorkflowTemplateError("template revision must be a bounded positive integer")
        _text(self.title, "title", 80)
        _text(self.description, "description", 512)
        if (
            type(self.settings) is not tuple
            or len(self.settings) > 8
            or any(
                type(item) is not tuple or len(item) != 2 or type(item[0]) is not str
                for item in self.settings
            )
        ):
            raise WorkflowTemplateError("template settings must be immutable bounded pairs")
        values = dict(self.settings)
        if len(values) != len(self.settings):
            raise WorkflowTemplateError("template settings cannot repeat a field")
        validate_workflow_settings(self.surface, values)
        if type(self.requirements) is not tuple or not 1 <= len(self.requirements) <= 8:
            raise WorkflowTemplateError("template requirements must be an immutable bounded tuple")
        for requirement in self.requirements:
            _text(requirement, "requirement", 160)

    def to_dict(self) -> dict[str, Any]:
        """Project new JSON containers, preserving the immutable definition."""
        value = {
            "schema_version": WORKFLOW_TEMPLATE_SCHEMA,
            "template_id": self.template_id,
            "revision": self.revision,
            "surface": self.surface,
            "title": self.title,
            "description": self.description,
            "settings": validate_workflow_settings(self.surface, dict(self.settings)),
            "requirements": list(self.requirements),
            "scope": "draft_only",
            "execution_authorized": False,
        }
        value["template_digest"] = _digest(value)
        return value


def _settings(**values: WorkflowSetting) -> tuple[tuple[str, WorkflowSetting], ...]:
    return tuple(values.items())


_TEMPLATES = (
    WorkflowTemplate(
        "chat.direct",
        "chat",
        "Direct answer",
        "Start a single-response draft with a bounded answer-token allowance.",
        _settings(max_tokens=1024, review_response=False),
        (
            "Choose an available model before sending.",
            "Review the token allowance before submitting your message.",
        ),
    ),
    WorkflowTemplate(
        "chat.reviewed",
        "chat",
        "Review and refine",
        "Prepare a reviewed response using the existing cooperative answer workflow.",
        _settings(max_tokens=2048, review_response=True),
        (
            "The selected model and cooperative review route must be available.",
            "Review role selections and the shared resource allowance before sending.",
        ),
    ),
    WorkflowTemplate(
        "studio.plan",
        "studio",
        "Bounded planning",
        "Stage a small studio planning budget with no child-job allowance.",
        _settings(
            max_steps=8,
            max_model_calls=4,
            max_jobs=0,
            max_output_tokens=1024,
            authorization_seconds=600,
            completion_mode="native",
        ),
        (
            "Choose an owned project and describe the goal.",
            "Choose plan or run mode explicitly; this starter changes neither execution nor edit permission.",
            "Inspect native core and toolchain readiness before requesting native execution.",
        ),
    ),
    WorkflowTemplate(
        "studio.original",
        "studio",
        "Original workflow",
        "Stage a bounded original-project iteration budget for the existing studio owner.",
        _settings(
            max_steps=12,
            max_model_calls=8,
            max_jobs=4,
            max_output_tokens=1024,
            authorization_seconds=1800,
            completion_mode="original",
        ),
        (
            "Choose an owned original project and verify the current source revision.",
            "Select execution mode and requested completion requirements separately.",
            "Authorize edits explicitly when the goal needs source changes.",
        ),
    ),
    WorkflowTemplate(
        "studio.measured",
        "studio",
        "Measured refinement budget",
        "Stage the finite budget used for baseline, candidate review and possible restoration.",
        _settings(
            max_steps=16,
            max_model_calls=16,
            max_jobs=6,
            max_output_tokens=1024,
            authorization_seconds=3600,
            completion_mode="original",
        ),
        (
            "Enable measured quality and select simulation and review separately.",
            "Authorize editing and incumbent restoration through the existing goal form.",
            "Actual matched reviews determine acceptance; this starter grants no quality certification.",
        ),
    ),
    WorkflowTemplate(
        "crawler.focused",
        "crawler",
        "Focused capture",
        "Stage a small capture budget without following links beyond the supplied pages.",
        _settings(max_requests=8, max_documents=4, max_bytes=2 * 1024 * 1024, max_depth=0),
        (
            "Supply public seed URLs and verify permitted hosts.",
            "Acknowledge capture consent and source-use rights separately.",
            "Creating a capture does not authorize unattended automation or downstream training.",
        ),
    ),
    WorkflowTemplate(
        "crawler.research",
        "crawler",
        "Research capture",
        "Stage the default bounded research capture across one level of permitted links.",
        _settings(max_requests=24, max_documents=16, max_bytes=8 * 1024 * 1024, max_depth=1),
        (
            "Supply public seed URLs and verify permitted hosts.",
            "Acknowledge capture consent and source-use rights separately.",
            "Inspect captured sources and freshness before requesting a reviewed reference.",
        ),
    ),
    WorkflowTemplate(
        "crawler.broad",
        "crawler",
        "Broader bounded capture",
        "Stage a larger finite capture while preserving the crawler's request and host protections.",
        _settings(max_requests=64, max_documents=32, max_bytes=16 * 1024 * 1024, max_depth=2),
        (
            "Review the larger request, byte and document budgets before creating the capture.",
            "Supply public seeds and acknowledge consent and source-use rights separately.",
            "Host admission, robots and source-use policies remain authoritative.",
        ),
    ),
)


def workflow_template_catalog() -> dict[str, Any]:
    """Return a fresh bounded catalog; availability and execution stay unclaimed."""
    if not 1 <= len(_TEMPLATES) <= MAX_WORKFLOW_TEMPLATES:
        raise WorkflowTemplateError("workflow catalog exceeds its template bound")
    identities = {template.template_id for template in _TEMPLATES}
    if len(identities) != len(_TEMPLATES):
        raise WorkflowTemplateError("workflow catalog repeats a template identity")
    catalog = {
        "schema_version": WORKFLOW_CATALOG_SCHEMA,
        "catalog_version": WORKFLOW_CATALOG_VERSION,
        "templates": [template.to_dict() for template in _TEMPLATES],
        "execution_authorized": False,
    }
    catalog["catalog_digest"] = _digest(catalog)
    if len(_canonical(catalog)) > MAX_WORKFLOW_CATALOG_BYTES:
        raise WorkflowTemplateError("workflow catalog exceeds its serialized byte bound")
    return catalog


def workflow_template(template_id: str) -> dict[str, Any]:
    """Look up one declared draft without materializing or starting a workflow."""
    identifier = _text(template_id, "template_id", 96)
    for template in _TEMPLATES:
        if template.template_id == identifier:
            return template.to_dict()
    raise WorkflowTemplateError("unknown workflow template")
