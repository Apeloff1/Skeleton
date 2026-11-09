#!/usr/bin/env python3
"""Validate historical receipt completeness without fabricating unavailable fields."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"machine/accountability_recovery_evidence.json"
FINAL={"ACC-VOL-000","ACC-VOL-034","ACC-VOL-035","ACC-VOL-036","ACC-VOL-037","ACC-VOL-038","ACC-VOL-078","ACC-VOL-079","ACC-VOL-080","ACC-VOL-420"}
def validate(d):
 errors=[]; a=next((x for x in d.get("anchors",[]) if x.get("source_pr")==2693),None)
 if not a:return ["missing PR #2693 recovery anchor"]
 if set(a.get("record_ids",[]))!=FINAL:errors.append("PR #2693 final-ten membership drift")
 if a.get("verification_signer")!="github-actions:P1 Evidence Identity Gate":errors.append("PR #2693 verifier identity drift")
 if a.get("automatic_signature_write_authorized") is not False:errors.append("final-ten automatic signature write must remain forbidden")
 if "cancelled/skipped" not in a.get("workflow_caveat",""):errors.append("missing cancelled/skipped workflow caveat")
 return errors
if __name__=="__main__":
 e=validate(json.loads(E.read_text()));print("final-ten receipt boundary: valid" if not e else "\\n".join(e));raise SystemExit(bool(e))
