"""retrieval_insertion: schedule — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.scheduler import FairQueue,Task
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import refuse
def enqueue(tasks,*,weight=1):
    if type(tasks) not in (tuple,list) or len(tasks)>4096:
        refuse("bounded real queued task collection required")
    queue=FairQueue(maximum=4096)
    for task in tasks:
        if type(task) is not Task:refuse("typed scheduled task required")
        queue.enqueue(task,weight=weight)
    return queue
def admit(queue,*,now_ns,tokens):
    if type(queue) is not FairQueue:refuse("fair native queue required")
    return queue.admit(now_ns=now_ns,capacity_tokens=tokens)
