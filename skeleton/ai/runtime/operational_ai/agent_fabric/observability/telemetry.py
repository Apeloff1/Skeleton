"""No-prompt observability: bounded integer aggregates only."""
from collections import Counter
from ..core.canonical import uint

def aggregate(receipts,*,limit=10000):
    uint(limit,'event count',1,100000)
    counts=Counter();durations=[]
    for i,row in enumerate(receipts):
        if i>=limit:raise ValueError('telemetry review bound exceeded')
        if not isinstance(row,dict) or set(row)!={'kind','status','elapsed_ms'}:raise ValueError('unexpected telemetry shape')
        if row['kind'] not in ('model','tool','read','review'):raise ValueError('unsupported work type')
        if row['status'] not in ('complete','held'):raise ValueError('unknown work status')
        ms=uint(row['elapsed_ms'],'duration',0,86400000)
        counts[(row['kind'],row['status'])]+=1;durations.append(ms)
    durations.sort()
    def q(p):return durations[min(len(durations)-1,int(p*(len(durations)-1)))] if durations else None
    return {'total':len(durations),'p50_ms':q(.5),'p95_ms':q(.95),
            'counts':{f'{k[0]}_{k[1]}':v for k,v in sorted(counts.items())},'content_logged':False}
