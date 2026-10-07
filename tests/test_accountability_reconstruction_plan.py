import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(p): return json.loads((ROOT/p).read_text())
def test_reconstruction_plan_is_non_mutating_and_complete():
 p=load("machine/accountability_reconstruction_plan.json")
 assert p["mode"]=="dry_run_only" and p["authority"]=="non_mutating_reconstruction_plan"
 assert p["record_count"]==len(p["records"])==170
 assert len({r["record_id"] for r in p["records"]})==170
 assert all("verification_signoff" in r["blocked"] and "completion" in r["blocked"] for r in p["records"])
def test_terminal_p1_members_are_represented_without_verification_promotion():
 e=load("machine/accountability_recovery_evidence.json");p=load("machine/accountability_reconstruction_plan.json")
 cohort=next(x for x in e["cohorts"] if x["name"]=="terminal_p1_retro_sign");by={r["record_id"]:r for r in p["records"]}
 for rid in cohort["membership_derivation"]["derived_record_ids"]:
  assert "implementation_signoff_presence" in by[rid]["recoverable"]
  assert "verification_signoff" in by[rid]["blocked"]
