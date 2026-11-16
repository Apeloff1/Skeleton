"""Exercise genuine canonical scene journeys through bounded portable bytes."""
from __future__ import annotations

from hashlib import sha256

from skeleton.app.recovered_evidence import EvidenceError, array, fields, integer, pin, seal, digest
from skeleton.game.gameplay.scene_travel import new_session, resume_session, verify_session
from skeleton.game.gameplay.scene_bytes import encode_scene_bytes, decode_scene_bytes

MAX_ACTIONS=256
MAX_CHECKPOINTS=32
MAX_AGGREGATE_BYTES=32*1024*1024


def qualify_scene(order,*,authorized):
    if authorized is not True:
        raise PermissionError("explicit scene qualification required")
    fields(order,{"schema","world","expected_source_digest","actions","checkpoint_interval","expected_phase"})
    if order["schema"]!="skeleton.scene-byte-qualification.order.v1":
        raise EvidenceError("unsupported scene byte order")
    actions=array(order["actions"],1,MAX_ACTIONS)
    interval=integer(order["checkpoint_interval"],1,MAX_ACTIONS)
    if (len(actions)+interval-1)//interval+1>MAX_CHECKPOINTS:
        raise EvidenceError("checkpoint count ceiling")
    expected_phase=order["expected_phase"]
    if expected_phase not in ("active","won","lost"):
        raise EvidenceError("unsupported requested end state")
    initial=new_session(order["world"])
    pin(initial["source_digest"],order["expected_source_digest"])
    uninterrupted=resume_session(initial,actions)
    resumed=initial
    checkpoints=[]
    total=0
    for offset in range(0,len(actions)+1,interval):
        payload=encode_scene_bytes(resumed)
        total+=len(payload)
        if total>MAX_AGGREGATE_BYTES:
            raise EvidenceError("aggregate portable custody byte ceiling")
        restored=decode_scene_bytes(payload)
        if restored!=resumed or encode_scene_bytes(restored)!=payload:
            raise EvidenceError("portable byte replay mismatch")
        pin(restored["source_digest"],order["expected_source_digest"])
        checkpoints.append({"actions_applied":offset,"byte_length":len(payload),
                            "sha256":sha256(payload).hexdigest(),
                            "state_digest":restored["state_digest"]})
        resumed=resume_session(restored,actions[offset:offset+interval])
    if resumed!=uninterrupted or verify_session(resumed)!=resumed:
        raise EvidenceError("checkpointed scene diverged from uninterrupted journey")
    if checkpoints[-1]["actions_applied"]!=len(actions):
        payload=encode_scene_bytes(resumed)
        total+=len(payload)
        if total>MAX_AGGREGATE_BYTES or decode_scene_bytes(payload)!=resumed:
            raise EvidenceError("terminal portable custody mismatch")
        checkpoints.append({"actions_applied":len(actions),"byte_length":len(payload),
                            "sha256":sha256(payload).hexdigest(),"state_digest":resumed["state_digest"]})
    phase=resumed["state"]["phase"]
    if phase!=expected_phase:
        raise EvidenceError("actual terminal state differs from requested qualification")
    return seal({"schema":"skeleton.scene-byte-qualification.report.v1",
                 "order_digest":digest(order),"source_digest":initial["source_digest"],
                 "checkpoints":checkpoints,"aggregate_portable_bytes":total,
                 "actions_executed":len(actions),"final_state_digest":resumed["state_digest"],
                 "phase":phase,"ending":resumed["state"]["ending"],
                 "canonical_scene_executed":True,"byte_reconstruction_matched":True,
                 "process_restart_tested":False,"native_engine_executed":False,"release_certified":False})
