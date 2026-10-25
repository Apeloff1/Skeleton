"""Executable anti-pattern governance for VOL-108."""
from __future__ import annotations
from dataclasses import dataclass
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class AntiPatternError(ValueError):pass
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise AntiPatternError(f"{f} must be stable identifier")
 return v
@dataclass(frozen=True,slots=True)
class AntiPattern:
 pattern_id:str;failure_history:str;detector_regex:str;preferred_alternative:str
 def __post_init__(self):
  object.__setattr__(self,"pattern_id",_id(self.pattern_id,"pattern_id"))
  if not isinstance(self.failure_history,str) or not isinstance(self.preferred_alternative,str) or not self.failure_history.strip() or not self.preferred_alternative.strip():raise AntiPatternError("history and alternative required")
  if not isinstance(self.detector_regex,str) or not self.detector_regex:raise AntiPatternError("detector regex required")
  try:re.compile(self.detector_regex)
  except re.error as e:raise AntiPatternError("invalid detector regex") from e
@dataclass(frozen=True,slots=True)
class AntiPatternFinding:
 pattern_id:str;path:str;line:int;excerpt:str
 def __post_init__(self):
  object.__setattr__(self,"pattern_id",_id(self.pattern_id,"pattern_id"))
  if not isinstance(self.path,str) or not self.path.strip() or not isinstance(self.line,int) or isinstance(self.line,bool) or self.line<1:raise AntiPatternError("finding location invalid")
  if not isinstance(self.excerpt,str):raise AntiPatternError("finding excerpt invalid")
@dataclass(frozen=True,slots=True)
class AntiPatternException:
 pattern_id:str;path:str;owner_id:str;rationale:str;expires_tick:int
 def __post_init__(self):
  object.__setattr__(self,"pattern_id",_id(self.pattern_id,"pattern_id"));object.__setattr__(self,"owner_id",_id(self.owner_id,"owner_id"))
  if not isinstance(self.path,str) or not self.path.strip() or not isinstance(self.rationale,str) or not self.rationale.strip() or not isinstance(self.expires_tick,int) or isinstance(self.expires_tick,bool) or self.expires_tick<1:raise AntiPatternError("exception owner rationale and expiry required")
class AntiPatternRegistry:
    """Fail-closed detector and time-scoped exception registry."""

    def __init__(self, patterns):
        items = tuple(patterns)
        if any(not isinstance(item, AntiPattern) for item in items):
            raise AntiPatternError("registry needs AntiPattern entries")
        ids = [item.pattern_id for item in items]
        if len(ids) != len(set(ids)):
            raise AntiPatternError("duplicate anti-pattern registry identity")
        self.patterns = {item.pattern_id: item for item in items}
        self._detectors = {
            item.pattern_id: re.compile(item.detector_regex) for item in items
        }

    def scan(self, path, text):
        if not isinstance(path, str) or not path.strip() or not isinstance(text, str):
            raise AntiPatternError("scan path and text must be strings")
        findings = []
        for pattern_id, regex in self._detectors.items():
            for line_no, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    findings.append(
                        AntiPatternFinding(pattern_id, path, line_no, line.strip())
                    )
        return tuple(sorted(findings, key=lambda item: (item.path, item.line, item.pattern_id)))

    def unresolved(self, findings, exceptions, current_tick):
        if type(current_tick) is not int or current_tick < 0:
            raise AntiPatternError("current_tick must be a nonnegative integer")
        active = set()
        for item in exceptions:
            if not isinstance(item, AntiPatternException):
                raise AntiPatternError("exception must be a governed AntiPatternException")
            if item.pattern_id not in self.patterns:
                raise AntiPatternError(f"unknown anti-pattern exception: {item.pattern_id}")
            if item.expires_tick >= current_tick:
                active.add((item.pattern_id, item.path))
        result = []
        for item in findings:
            if not isinstance(item, AntiPatternFinding):
                raise AntiPatternError("finding must be a governed AntiPatternFinding")
            if item.pattern_id not in self.patterns:
                raise AntiPatternError(f"unknown anti-pattern finding: {item.pattern_id}")
            if (item.pattern_id, item.path) not in active:
                result.append(item)
        return tuple(result)
