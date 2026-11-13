"""Closed v2 native transport envelope and reproducible capability surface."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from ...authority.canonical import ContractViolation

SCHEMA='skeleton.ai.native-flight-http.v2'
PROTOCOL={
  'schema':SCHEMA,
  'transport':'loopback-bearer-only',
  'required_model':'approved-local-native-GGUF',
  'event_stream':{'method':'GET','route':'/v2/jobs/{job_id}/events',
                  'authentication':'private-bearer-and-hmac-job-cursor',
                  'max_events':32,'max_wait_ms':2000,
                  'delivery':'finite-resumable-SSE-verified-status-only'},
  'operations':{
    'create':['session_id'],
    'submit':['job_id','session_id','request_id','question'],
    'work_one':[],
    'cancel':['job_id'],
    'wait':['job_id'],
    'job':['job_id'],
    'queue':[],
    'history':['session_id'],
    'replay':['session_id','request_id','question'],
    'knowledge_search':['question'],
  },
  'privileged_operator_actions':'not-exposed-over-http',
  'model_tool_execution':'not-exposed-over-http',
  'actual_release_state':'draft-not-certified',
}
OPTIONAL={
    'submit':('priority','seed','temperature'),
    'replay':('seed','temperature'),
    'knowledge_search':('limit',),
    'wait':('max_wait_ms',),
}


def validate_payload(operation: str, data: dict[str,Any])->None:
    if operation not in PROTOCOL['operations'] or type(data) is not dict:
        raise ContractViolation('unknown native flight operation or payload')
    required=set(PROTOCOL['operations'][operation]);optional=set(OPTIONAL.get(operation,()))
    if not required.issubset(data) or set(data)-required-optional:
        raise ContractViolation('unexpected or missing flight operation fields')
