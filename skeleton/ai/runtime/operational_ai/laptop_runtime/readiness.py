"""Observational readiness; native activation already occurred outside this module."""
from __future__ import annotations
from .contracts import refuse
from .identity import ActiveModel

def snapshot(worker):
    active=ActiveModel.from_supervisor(worker)
    try:
        status=worker.status()
        doctor=worker.spine.health()
    except Exception:
        return {"state":"held","reason":"live-observation-unavailable",
                "model_sha256":active.model_sha256,
                "native_inference_qualified":False,
                "release_certified":False}
    if type(status) is not dict or type(doctor) is not dict:
        refuse("invalid observed runtime health")
    return {"state":"native-model-activated-observation-only",
            "identity":active.to_record(),"supervisor":status,
            "doctor":doctor,"native_inference_qualified":False,
            "release_certified":False}

def release_holds():
    return {"native_model_e2e":False,"approved_model_rights":False,
            "clean_laptop_installation":False,"device_performance":False,
            "exact_head_github_checks":False,"independent_review":False,
            "release_certified":False}
