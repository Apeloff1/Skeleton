"""Conservative backpressure admission from exact measured queue inventories."""
from ..core.canonical import uint

def admit(*,running:int,queued:int,max_running:int,max_queued:int):
    uint(running,'running',0,1000000);uint(queued,'queued',0,1000000)
    uint(max_running,'running limit',1,1000000);uint(max_queued,'queued limit',1,1000000)
    return {'admitted':running<max_running and queued<max_queued,
            'capacity_left':max(0,max_queued-queued),
            'status':'observed-queue-only-not-model-capacity-certified'}
