"""Deterministic integration validation plan for the aggregate autonomous build."""
from __future__ import annotations
from pathlib import PurePosixPath
from typing import Iterable
def integration_commands(paths:Iterable[str])->tuple[tuple[str,...],...]:
 p=tuple(sorted(set(paths))); py=tuple(x for x in p if x.endswith(".py"))
 tests=tuple(x for x in py if "/test" in x or PurePosixPath(x).name.startswith("test_"))
 commands=[]
 if tests: commands.append(("python","-m","pytest","-q",*tests[:12]))
 if py: commands.append(("python","-m","compileall","-q",*py[:12]))
 # Aggregate Studio regression is fixed, never model-authored.
 if any(x.startswith("skeleton/automation/") for x in p):
  commands.append(("python","-m","pytest","-q","skeleton/testing/test_supervised_studio.py","skeleton/testing/test_studio_director.py"))
 return tuple(commands[:3])
