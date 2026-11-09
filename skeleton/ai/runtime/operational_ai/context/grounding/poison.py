"""Non-authoritative prompt-injection heuristics for untrusted evidence inspection.

Heuristics never authorize content; they can only quarantine suspicious data.
No clean heuristic result upgrades a source to an instruction authority.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from .documents import Passage
_PATTERNS={
 'role-spoof':re.compile(r'(?i)(?:^|\n)\s*(system|developer|assistant)\s*:'),
 'instruction-override':re.compile(r'(?i)ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions'),
 'tool-exfil':re.compile(r'(?i)(?:curl|wget|fetch)\s+https?://|send\s+your\s+api\s+key'),
 'prompt-prefix':re.compile(r'(?i)\[INST\]|<\|im_start\|>|<\|system\|>'),
 'dangerous-tool':re.compile(r'(?i)(?:delete|remove|drop)\s+(?:all\s+)?(?:files|database|secrets)'),
}
@dataclass(frozen=True,slots=True)
class InjectionFinding:
    rule:str
    start:int
    end:int
    excerpt:str


def scan_passage(passage:Passage,*,maximum:int=32)->tuple[InjectionFinding,...]:
    out=[]
    for rule,pattern in _PATTERNS.items():
        for m in pattern.finditer(passage.body):
            if len(out)>=maximum:return tuple(out)
            out.append(InjectionFinding(rule,passage.start+m.start(),passage.start+m.end(),m.group()[:100]))
    return tuple(sorted(out,key=lambda e:(e.start,e.rule)))
