"""
Operational Prompt Template. House-copy style templating with era_bind and pointer clauses.
Fills the prompt construction gap.
"""
from typing import Dict

class PromptTemplate:
    def __init__(self):
        self.templates = {
            "default": "{era} {prompt}",
            "house": "HOUSE_ERA: {prompt} | seams={seams}"
        }

    def render(self, name: str, **kwargs) -> str:
        tpl = self.templates.get(name, self.templates["default"])
        return tpl.format(**kwargs)

    def add(self, name: str, template: str) -> None:
        self.templates[name] = template
