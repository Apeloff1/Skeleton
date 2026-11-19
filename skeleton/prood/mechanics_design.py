"""Bounded reproducible economy and playable layout design primitives."""
from collections import deque
from skeleton.prood.world_design import seeded


def build_economy(ctx, seat, quest):
    rng=seeded(ctx["seed"],"mechanics",seat)
    scarcity=ctx["axes"].get("scarcity",.5)
    risk=ctx["axes"].get("risk",.5)
    grind=ctx["axes"].get("grind",.5)
    balance=30
    rows=[]
    for index, step in enumerate(quest["steps"]):
        income=16+int(18*(1-scarcity))+index*3+rng.randrange(7)
        cost=8+int(10*risk)+int(grind*5)+index
        opening=balance
        # Required progression cannot depend on an unpayable mandatory sink.
        cost=min(cost,opening+income)
        balance=opening+income-cost
        rows.append({"quest":step["id"],"opening":opening,"income":income,"cost":cost,"closing":balance})
    return {"currency":"salvage","initial":30,"steps":rows,"final":balance,
            "minimum_balance":min([30]+[row["closing"] for row in rows])}


def validate_economy(economy,quest):
    rows=economy["steps"]
    if len(rows)!=len(quest["steps"]) or economy["initial"]!=30:
        raise ValueError("economy and quest lengths differ")
    balance=30
    minimum=balance
    for row,step in zip(rows,quest["steps"]):
        if row["quest"]!=step["id"] or row["opening"]!=balance:
            raise ValueError("economy sequence mismatch")
        if any(type(row[k]) is not int or row[k]<0 for k in ("income","cost","closing")):
            raise ValueError("invalid economic amount")
        balance=balance+row["income"]-row["cost"]
        if balance<0 or row["closing"]!=balance:
            raise ValueError("invalid economy balance")
        minimum=min(minimum,balance)
    if economy["final"]!=balance or economy["minimum_balance"]!=minimum:
        raise ValueError("economy summary mismatch")


def build_maze(ctx, seat):
    size=ctx["grid_size"]
    rng=seeded(ctx["seed"],"procedural",seat)
    grid=[["#"]*size for _ in range(size)]
    stack=[(1,1)]
    grid[1][1]="."
    while stack:
        x,y=stack[-1]
        choices=[(x+dx,y+dy) for dx,dy in ((2,0),(-2,0),(0,2),(0,-2))
                 if 0<x+dx<size-1 and 0<y+dy<size-1 and grid[y+dy][x+dx]=="#"]
        if not choices:
            stack.pop()
            continue
        nx,ny=rng.choice(choices)
        grid[(y+ny)//2][(x+nx)//2]="."
        grid[ny][nx]="."
        stack.append((nx,ny))
    result={"width":size,"height":size,"rows":["".join(row) for row in grid],
            "entry":[1,1],"exit":[size-2,size-2]}
    result["path_length"]=maze_distance(result)
    return result


def maze_distance(maze):
    width,height=maze["width"],maze["height"]
    rows=maze["rows"]
    if (type(width) is not int or type(height) is not int or not 5<=width<=31 or not 5<=height<=31
            or len(rows)!=height or any(type(row) is not str or len(row)!=width or set(row)-{"#","."} for row in rows)):
        raise ValueError("invalid bounded maze")
    if any(c!="#" for c in rows[0]+rows[-1]) or any(row[0]!="#" or row[-1]!="#" for row in rows):
        raise ValueError("maze boundary is open")
    entry,goal=tuple(maze["entry"]),tuple(maze["exit"])
    for point in (entry,goal):
        if len(point)!=2 or any(type(v) is not int for v in point):
            raise ValueError("invalid maze endpoint")
        x,y=point
        if not 0<x<width-1 or not 0<y<height-1 or rows[y][x]!=".":
            raise ValueError("maze endpoint is not traversable")
    if entry==goal:
        raise ValueError("identical maze endpoints")
    queue=deque([(entry,0)])
    seen={entry}
    answer=None
    while queue:
        (x,y),d=queue.popleft()
        if (x,y)==goal:
            answer=d
        for nx,ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if 0<=nx<width and 0<=ny<height and rows[ny][nx]=="." and (nx,ny) not in seen:
                seen.add((nx,ny))
                queue.append(((nx,ny),d+1))
    if answer is None or len(seen)!=sum(row.count(".") for row in rows):
        raise ValueError("disconnected maze")
    return answer
