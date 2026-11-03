"""Persist grant redemption *before* potentially irreversible effects."""
from hashlib import sha256
from ..core.canonical import canonical
from ..core.errors import Unauthorized,Conflict
from .grants import Grant,verify
import time

def redeem(db,key:bytes,grant:Grant,*,plan,step,resource,operation,arguments):
    verify(key,grant,now_ns=time.time_ns(),plan=plan,step=step,resource=resource,
           operation=operation,arguments=arguments)
    raw=canonical(grant.record(),ceiling=8192);digest=sha256(raw).hexdigest()
    with db.transaction() as conn:
        row=conn.execute('SELECT approval_sha,redeemed FROM agent_approvals WHERE plan_id=? AND step_id=?',(plan,step)).fetchone()
        if row:
            if row[0]!=digest:raise Conflict('inconsistent approval for step')
            raise Unauthorized('grant already redeemed or custody ambiguous')
        conn.execute('INSERT INTO agent_approvals VALUES (?,?,?,?,1)',(plan,step,digest,raw))
    # The caller executes only once after this durable boundary.
    return digest
