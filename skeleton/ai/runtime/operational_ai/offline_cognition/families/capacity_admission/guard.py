"""capacity_admission: finite machine-resource admission and output reconciliation facade."""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import refuse
from skeleton.ai.runtime.operational_ai.offline_cognition.core.capacity_guard import (
    CapacitySnapshot,ResourceRequest,QuotaProjection,preview,pressure_gate,
    fair_preview,preemption_hold,
)

def evaluate(snapshot,requests,*,now_ns):
    if type(snapshot) is not CapacitySnapshot:refuse("typed snapshot required")
    if len(requests)>512:refuse("family admission batch ceiling")
    return preview(snapshot,requests,now_ns=now_ns)

def pressure(snapshot,*,now_ns,memory_bytes,disk_bytes):
    return pressure_gate(snapshot,now_ns=now_ns,
                         memory_guard_bytes=memory_bytes,disk_guard_bytes=disk_bytes)

def reserve_projection(scope,*,epoch,tokens):
    if tokens>PROFILE.context_limit:refuse("token family ceiling")
    return QuotaProjection(scope,epoch=epoch,token_ceiling=tokens)

def queue_preview(tasks,weights,*,now_ns,token_capacity):
    if token_capacity>PROFILE.context_limit:refuse("family queue token ceiling")
    return fair_preview(tasks,weights,now_ns=now_ns,token_capacity=token_capacity)

def request_preemption(request,*,dispatched,operator_approved):
    return preemption_hold(request,dispatched=dispatched,
                           operator_approved=operator_approved)

def limits():
    return {"family":PROFILE.name,"token_budget":PROFILE.context_limit,
            "byte_budget":PROFILE.byte_limit,"max_batch":512,
            "durable_work_order_authority_here":False,
            "device_profile_qualified":False,"native_execution_performed":False}
