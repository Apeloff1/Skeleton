"""Sequential, pressure-revalidated execution of fixed assurance owners."""
from __future__ import annotations

from dataclasses import asdict
import time

from skeleton.app.resource_assurance import AdmissionPolicy, AdmissionGate, observe, selected_suites
from skeleton.app.local_source_assurance import qualify, inventory
from skeleton.app.recovered_evidence import EvidenceError, seal, verify, digest

SCHEMA="skeleton.resource-assurance.report.v1"


def run_campaign(names, *, authorized, policy=AdmissionPolicy(), repeat=False,
                 previous=None, previous_digest=None):
    if authorized is not True:
        raise PermissionError("explicit source assurance operator required")
    if type(repeat) is not bool or not isinstance(policy,AdmissionPolicy):
        raise EvidenceError("invalid execution policy")
    selected=selected_suites(names)
    inventory_digest=inventory()["digest"]
    # Prior reports are history only. Every selected owner must run again.
    prior=None
    if previous is not None:
        verify(previous,previous_digest)
        if (previous.get("schema")!=SCHEMA or previous.get("inventory_digest")!=inventory_digest
                or previous.get("selection")!=list(selected)):
            raise EvidenceError("previous campaign identity mismatch")
        prior=previous["digest"]
    elif previous_digest is not None:
        raise EvidenceError("unexpected historical digest")
    gate=AdmissionGate(policy)
    records=[]
    pressure=[]
    stopped=False
    for name in selected:
        if stopped:
            records.append({"suite":name,"state":"held_after_pressure","evidence":None})
            continue
        decision=None
        before=[]
        try:
            for index in range(policy.sample_count):
                if index and policy.interval_ms:
                    time.sleep(policy.interval_ms/1000)
                sample=observe()
                decision=gate.step(sample,now_ns=time.monotonic_ns())
                before.append(decision)
                # A critical observation cannot be bypassed by subsequent
                # healthy samples in the same admission window.
                if decision["reason"] in {"cpu_thermal_critical","battery_critical",
                      "stale_or_overlapping_probe","memory_observation_missing",
                      "stale_or_future_telemetry","replayed_source_telemetry"}:
                    break
        except (ValueError,OSError,RuntimeError) as exc:
            records.append({"suite":name,"state":"held_probe_error","evidence":None,
                            "error_class":type(exc).__name__})
            stopped=True
            continue
        pressure.append({"suite":name,"before":before})
        if decision is None or decision["workers"]<1:
            records.append({"suite":name,"state":"held_resource_budget","evidence":None})
            stopped=True
            continue
        # Synchronous known-owner call; no arbitrary executable and no
        # concurrent suite launches. Admission is advisory during execution.
        started=time.monotonic_ns()
        result=qualify([name],authorized=True,repeat=repeat)
        ended=time.monotonic_ns()
        state="passed" if result["selected_source_suites_passed"] else "failed"
        try:
            after=gate.step(observe(),now_ns=time.monotonic_ns())
        except (ValueError,OSError,RuntimeError) as exc:
            after={"workers":0,"reason":"post_execution_probe_error","error_class":type(exc).__name__}
        pressure[-1]["after"]=after
        records.append({"suite":name,"state":state,"evidence":result,
                        "duration_ns":ended-started,"post_execution_pressure":after["workers"]<1})
        if after["workers"]<1:
            stopped=True
    passed=sum(row["state"]=="passed" for row in records)
    return seal({"schema":SCHEMA,"selection":list(selected),"policy":asdict(policy),
                 "inventory_digest":inventory_digest,"previous_report_digest":prior,
                 "records":records,"pressure":pressure,"passed_suites":passed,
                 "held_suites":sum(row["state"].startswith("held") for row in records),
                 "completed_selection":passed==len(selected),
                 "accounted_cases":sum(row["evidence"]["accounted_first_pass_cases"]
                     for row in records if row["evidence"] is not None),
                 "sequential_execution":True,"physical_resource_reservation":False,
                 "inflight_preemption":False,"native_model_tested":False,"release_certified":False})
