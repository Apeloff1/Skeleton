from __future__ import annotations
import hashlib,json,sys
import pytest
from skeleton.native.isolation import AcceleratorIsolationError,run_json_process
from skeleton.native.selection import ProfileEvidence,SelectionPolicy,evaluate_candidate

_ECHO="import json,sys;p=json.loads(sys.stdin.buffer.read());sys.stdout.write(json.dumps({'seen':p},sort_keys=True,separators=(',',':')))"

def test_subprocess_receipt_binds_request_response_and_has_no_execution_authority():
 payload={"value":7}
 result=run_json_process([sys.executable,"-c",_ECHO],payload,timeout_s=5)
 request=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
 response=json.dumps(result.payload,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
 assert result.request_digest==hashlib.sha256(request).hexdigest()
 assert result.response_digest==hashlib.sha256(response).hexdigest()
 assert result.isolation_mode=="subprocess-json"
 assert result.authority_scope=="native-isolation-evidence-only"

def test_crash_prone_candidate_cannot_qualify_without_isolation():
 evidence=[ProfileEvidence(f"e{i}","native","src","env",64,1000,400,True,0.0) for i in range(2)]
 decision=evaluate_candidate(candidate_id="native",current_source_identity="src",reference_available=True,isolation_satisfied=False,protocol_compatible=True,evidence=evidence,policy=SelectionPolicy())
 assert decision.route=="reference"
 assert "isolation_requirement_unsatisfied" in decision.reason_codes

def test_isolated_crash_never_becomes_success_receipt():
 with pytest.raises(AcceleratorIsolationError,match="exited"):
  run_json_process([sys.executable,"-c","raise SystemExit(23)"],{"value":7},timeout_s=5)


def test_isolation_receipt_digest_is_order_independent_for_mapping_payloads():
 first=run_json_process([sys.executable,"-c",_ECHO],{"a":1,"b":2},timeout_s=5)
 second=run_json_process([sys.executable,"-c",_ECHO],{"b":2,"a":1},timeout_s=5)
 assert first.request_digest==second.request_digest
 assert first.response_digest==second.response_digest

def test_isolation_rejects_nonfinite_request_before_process_start():
 with pytest.raises(AcceleratorIsolationError,match="canonical-JSON"):
  run_json_process([sys.executable,"-c",_ECHO],{"value":float("nan")},timeout_s=5)


def test_speedup_cannot_compensate_for_isolation_failure():
 evidence=[ProfileEvidence(f"fast-{i}","native","src","env",128,1000000,1,True,0.0) for i in range(2)]
 decision=evaluate_candidate(candidate_id="native",current_source_identity="src",reference_available=True,isolation_satisfied=False,protocol_compatible=True,evidence=evidence,policy=SelectionPolicy())
 assert not decision.qualified
 assert decision.route=="reference"
 assert decision.worst_speedup==1000000.0
 assert decision.reason_codes==("isolation_requirement_unsatisfied",)
