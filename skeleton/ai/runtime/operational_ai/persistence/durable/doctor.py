"""Read-only operational recovery doctor; no implicit data rewrite or promotion."""
from __future__ import annotations
from .database import DurableDatabase,DurableError
from .eventlog import OperationEvents
from .operations import OperationRepository


def inspect(db:DurableDatabase,*,maximum:int=10_000)->dict:
    if type(maximum) is not int or not 1<=maximum<=100_000:
        raise DurableError('invalid audit scan cap')
    state=db.check()
    if state['status']!='ok' or not state['foreign_keys']:
        return {'status':'not-qualified','reason':'database-integrity','checked':0}
    rows=db.query('SELECT tenant,owner,operation FROM ai_operation ORDER BY tenant,owner,operation LIMIT ?', (maximum+1,))
    if len(rows)>maximum:
        return {'status':'not-qualified','reason':'scan-budget-exceeded','checked':0}
    problems=[];checked=0
    reader=OperationEvents(db)
    for key in rows:
        try:
            reader.replay(*key)
            OperationRepository(db).get(*key)
            checked+=1
        except Exception as exc:
            problems.append({'operation':key,'reason':str(exc)[:200]})
    return {'status':'verified' if not problems else 'not-qualified',
            'checked':checked,'problems':problems,'db':state}
