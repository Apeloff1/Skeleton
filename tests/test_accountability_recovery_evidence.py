from copy import deepcopy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from check_accountability_recovery_evidence import validate

def evidence(): return json.loads((ROOT/"machine/accountability_recovery_evidence.json").read_text())
def test_recovery_manifest_is_fail_closed(): assert validate(evidence())==[]
def test_retro_sign_membership_is_exact():
 d=evidence(); c=next(x for x in d["cohorts"] if x["name"]=="terminal_p1_retro_sign"); ids=c["membership_derivation"]["derived_record_ids"]
 assert len(ids)==len(set(ids))==103
 assert not {"ACC-VOL-013","ACC-VOL-014","ACC-VOL-253","ACC-VOL-248"}.intersection(ids)
def test_implementation_anchor_cannot_promote_verification():
 d=evidence(); a=next(x for x in d["anchors"] if str(x.get("recovery_granularity","")).startswith("implementation_signoff")); bad=deepcopy(d); target=next(x for x in bad["anchors"] if x["record_ids"]==a["record_ids"]); target["verification_state"]="verified"
 assert any("may not promote verification" in e for e in validate(bad))
def test_cohort_cannot_invent_completion():
 d=evidence(); bad=deepcopy(d); next(x for x in bad["cohorts"] if x["name"]=="terminal_p1_retro_sign")["completion_checkboxes_added"]=1
 assert any("may not imply completion" in e for e in validate(bad))
