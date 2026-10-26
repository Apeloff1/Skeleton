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
    """Deterministic fail-closed detector and time-bounded exception registry."""

    def __init__(self, patterns):
        if not isinstance(patterns, (tuple, list)):
            raise AntiPatternError("patterns must be a bounded sequence")
        if any(not isinstance(pattern, AntiPattern) for pattern in patterns):
            raise AntiPatternError("registry requires typed AntiPattern entries")
        ids = [pattern.pattern_id for pattern in patterns]
        if len(ids) != len(set(ids)):
            raise AntiPatternError("duplicate anti-pattern registry identity")
        self.patterns = {pattern.pattern_id: pattern for pattern in patterns}
        self._detectors = {
            pattern.pattern_id: re.compile(pattern.detector_regex) for pattern in patterns
        }

    def scan(self, path, text):
        if not isinstance(path, str) or not path.strip() or not isinstance(text, str):
            raise AntiPatternError("scan path and text must be strings")
        findings = []
        for pattern_id, detector in self._detectors.items():
            for number, line in enumerate(text.splitlines(), 1):
                if detector.search(line):
                    findings.append(
                        AntiPatternFinding(pattern_id, path, number, line.strip())
                    )
        return tuple(sorted(findings, key=lambda item: (item.path, item.line, item.pattern_id)))

    def unresolved(self, findings, exceptions, current_tick):
        if type(current_tick) is not int or current_tick < 0:
            raise AntiPatternError("current_tick must be nonnegative integer")
        if not isinstance(findings, (tuple, list)) or any(
            not isinstance(item, AntiPatternFinding) for item in findings
        ):
            raise AntiPatternError("findings must be a bounded typed sequence")
        if not isinstance(exceptions, (tuple, list)) or any(
            not isinstance(item, AntiPatternException) for item in exceptions
        ):
            raise AntiPatternError("exceptions must be a bounded typed sequence")
        if any(item.pattern_id not in self.patterns for item in findings):
            raise AntiPatternError("finding references unknown anti-pattern")
        if any(item.pattern_id not in self.patterns for item in exceptions):
            raise AntiPatternError("exception references unknown anti-pattern")
        identities = [(item.pattern_id, item.path) for item in exceptions]
        if len(identities) != len(set(identities)):
            raise AntiPatternError("duplicate exception identity")
        active = {
            (item.pattern_id, item.path)
            for item in exceptions
            if item.expires_tick >= current_tick
        }
        return tuple(
            item for item in findings if (item.pattern_id, item.path) not in active
        )
