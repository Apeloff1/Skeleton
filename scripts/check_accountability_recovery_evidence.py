#!/usr/bin/env python3
"""Validate fail-closed accountability recovery evidence."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RECOVERY=ROOT/"machine/accountability_recovery_evidence.json"

def validate(data):
 errors=[]
 if data.get("status")!="recovery_evidence_only": errors.append("status must remain recovery_evidence_only")
 seen=set()
 for i,a in enumerate(data.get("anchors",[])):
  ids=a.get("record_ids",[])
  if not ids: errors.append(f"anchor[{i}] has no record_ids")
  if len(ids)!=len(set(ids)): errors.append(f"anchor[{i}] has duplicate record_ids")
  for rid in ids:
   if not rid.startswith("ACC-"): errors.append(f"invalid accountability id: {rid}")
  gran=a.get("recovery_granularity","")
  if gran.startswith("implementation_signoff"):
   if a.get("verification_state") not in (None,"explicitly_unsigned","not_promoted_by_anchor"):
    errors.append(f"anchor[{i}] implementation evidence may not promote verification")
   if a.get("completion_state") not in (None,"explicitly_open"):
    errors.append(f"anchor[{i}] implementation evidence may not promote completion")
  seen.update(ids)
 cohorts={x.get("name"):x for x in data.get("cohorts",[])}
 c=cohorts.get("terminal_p1_retro_sign")
 if not c: errors.append("missing terminal_p1_retro_sign cohort")
 else:
  md=c.get("membership_derivation",{}); ids=md.get("derived_record_ids",[])
  if md.get("derived_count")!=103 or len(ids)!=103 or len(set(ids))!=103: errors.append("terminal P1 retro-sign membership must contain exactly 103 unique records")
  excluded={"ACC-VOL-013","ACC-VOL-014","ACC-VOL-253","ACC-VOL-248"}
  if excluded.intersection(ids): errors.append("terminal P1 retro-sign membership includes excluded pre-signed/completed records")
  if c.get("verification_signatures_added")!=0: errors.append("retro-sign cohort may not imply verification signatures")
  if c.get("completion_checkboxes_added")!=0: errors.append("retro-sign cohort may not imply completion")
 return errors

def main():
 data=json.loads(RECOVERY.read_text(encoding="utf-8")); errors=validate(data)
 if errors:
  for e in errors: print(f"ERROR: {e}")
  raise SystemExit(1)
 print("accountability recovery evidence: valid")
if __name__=="__main__": main()
