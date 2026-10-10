#!/usr/bin/env python3
"""Deterministic local/exact-head verification entrypoint for the crawler plane."""
from __future__ import annotations
import compileall,glob,subprocess,sys
def main()->int:
 if not compileall.compile_dir("skeleton/ai/webcrawler",quiet=1):
  return 2
 tests=sorted(glob.glob("tests/test_ai_webcrawler_*.py"))
 if not tests:
  print("no crawler tests discovered",file=sys.stderr);return 3
 return subprocess.call([sys.executable,"-m","pytest","-q","--noconftest",*tests])
if __name__=="__main__":raise SystemExit(main())
