"""Prompt templates for Jeeves — principled, reusable tutor messaging.

Tutor prompts shouldn't be assembled in handlers. The registry keeps
named templates with strict placeholders, and rend(prompt) injects
a versioned persona/context pair.
"""

from __future__ import annotations

from dataclasses import dataclass
from string import Template
from typing import Dict, Optional, Tuple

from skeleton.kernel.errors import KernelError


class TemplateError(KernelError):
    code = "JEE.TEMPLATES"


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    template: Template

    def render(self, **values: str) -> str:
        try:
            return self.template.substitute(values)
        except KeyError as exc:
            raise TemplateError(
                "missing placeholder",
                context={"template": self.name, "missing": str(exc)},
            )


class PromptRegistry:
    """Named templates used across the tutor surface."""

    def __init__(self) -> None:
        self._templates: Dict[str, PromptTemplate] = {}

    def register(self, name: str, template_str: str) -> PromptTemplate:
        template = PromptTemplate(name=name, template=Template(template_str))
        self._templates[name] = template
        return template

    def get(self, name: str) -> PromptTemplate:
        template = self._templates.get(name)
        if template is None:
            raise TemplateError("unknown template", context={"name": name})
        return template

    def render(self, name: str, **values: str) -> str:
        return self.get(name).render(**values)

    def names(self) -> Tuple[str, ...]:
        return tuple(sorted(self._templates))
