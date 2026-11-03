"""Deterministic tenant fairness selection, not FIFO starvation."""
from ..core.canonical import uint,identifier
from ..core.errors import Invalid

def select(rows,active):
    if not isinstance(rows,list) or not isinstance(active,dict):raise Invalid('invalid queue inventory')
    scored=[]
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'tenant','id','priority','created_ns'}:raise Invalid('invalid queue item')
        identifier(row['tenant'],'tenant');identifier(row['id'],'job')
        uint(row['priority'],'priority',0,100);uint(row['created_ns'],'creation time')
        a=active.get(row['tenant'],0);uint(a,'active tenant count',0,1000000)
        scored.append((a,-row['priority'],row['created_ns'],row['id'],row))
    return min(scored,key=lambda r:r[:4])[-1] if scored else None
