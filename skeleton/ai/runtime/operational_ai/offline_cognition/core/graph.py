"""Bounded deterministic DAG validation, scheduling, reachability and paths."""
from __future__ import annotations
import heapq
from .contracts import identifier,integer,refuse
def topological(nodes,edges,*,maximum=10000):
    integer(maximum,minimum=1,maximum=100000)
    if type(nodes) not in (tuple,list,set,frozenset) or len(nodes)>maximum:
        refuse("graph vertex ceiling")
    names=tuple(sorted(identifier(n) for n in nodes))
    if len(set(names))!=len(names):refuse("duplicate graph vertex")
    if type(edges) not in (tuple,list) or len(edges)>maximum*16:
        refuse("graph edge ceiling")
    indegree={n:0 for n in names}
    outbound={n:set() for n in names}
    for edge in edges:
        if type(edge) not in (tuple,list) or len(edge)!=2:
            refuse("graph edge requires origin/destination")
        src,dst=edge
        if src not in indegree or dst not in indegree or src==dst:
            refuse("unknown/self-referential graph edge")
        if dst in outbound[src]:refuse("duplicate graph dependency")
        outbound[src].add(dst);indegree[dst]+=1
    ready=[n for n in names if indegree[n]==0]
    heapq.heapify(ready)
    ordered=[]
    while ready:
        node=heapq.heappop(ready)
        ordered.append(node)
        for target in sorted(outbound[node]):
            indegree[target]-=1
            if indegree[target]==0:heapq.heappush(ready,target)
    if len(ordered)!=len(names):refuse("cycle in approved agent dependency graph")
    return tuple(ordered)
def descendants(nodes,edges,start):
    order=topological(nodes,edges)
    if start not in order:refuse("unknown starting node")
    outbound={}
    for src,dst in edges:outbound.setdefault(src,set()).add(dst)
    seen=set();frontier=[start]
    while frontier:
        node=frontier.pop()
        for neighbor in outbound.get(node,()):
            if neighbor not in seen:seen.add(neighbor);frontier.append(neighbor)
    return tuple(sorted(seen))
def critical_path(nodes,edges,durations):
    order=topological(nodes,edges)
    if type(durations) is not dict or set(durations)!=set(order):
        refuse("all task durations must be explicit")
    distance={}
    route={}
    prior={}
    for src,dst in edges:prior.setdefault(dst,[]).append(src)
    for task in order:
        delay=integer(durations[task],minimum=0,maximum=1_000_000_000)
        predecessors=prior.get(task,())
        if not predecessors:
            distance[task]=delay;route[task]=(task,)
        else:
            best=max(predecessors,key=lambda k:(distance[k],tuple(reversed(route[k]))))
            distance[task]=distance[best]+delay
            route[task]=route[best]+(task,)
    if not order:return {"length":0,"path":()}
    end=max(order,key=lambda k:(distance[k],tuple(reversed(route[k]))))
    return {"length":distance[end],"path":route[end]}
