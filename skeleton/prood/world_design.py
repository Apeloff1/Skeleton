"""Original deterministic regional graph and traversable quest generation."""
from collections import deque
from hashlib import sha256
import random

from skeleton.prood.design_contract import digest


def seeded(seed, kind, seat):
    return random.Random(int.from_bytes(sha256(f"{seed}:{kind}:{seat}".encode()).digest()[:16], "big"))


def distances(graph, start):
    found = {start: 0}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for neighbour in sorted(graph[node]):
            if neighbour not in found:
                found[neighbour] = found[node] + 1
                queue.append(neighbour)
    return found


def validate_world(world):
    if type(world) is not dict or set(world) != {"regions", "edges", "entry", "exit", "diameter"}:
        raise ValueError("invalid world graph")
    regions = world["regions"]
    if type(regions) is not list or not 3 <= len(regions) <= 24:
        raise ValueError("invalid region inventory")
    ids = [row["id"] for row in regions]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate region")
    graph = {rid: set() for rid in ids}
    if type(world["edges"]) is not list or len(world["edges"]) > len(ids)*(len(ids)-1)//2:
        raise ValueError("invalid edge inventory")
    for edge in world["edges"]:
        if type(edge) is not list or len(edge) != 2:
            raise ValueError("invalid edge")
        a, b = edge
        if a not in graph or b not in graph or a == b or b in graph[a]:
            raise ValueError("invalid or duplicate world edge")
        graph[a].add(b)
        graph[b].add(a)
    if world["entry"] not in graph or world["exit"] not in graph or world["entry"] == world["exit"]:
        raise ValueError("invalid world endpoints")
    maps = [distances(graph, key) for key in sorted(graph)]
    if any(len(row) != len(graph) for row in maps):
        raise ValueError("unreachable world region")
    if world["diameter"] != max(max(row.values()) for row in maps):
        raise ValueError("world diameter does not match graph")
    return graph


def build_world(ctx, seat):
    rng = seeded(ctx["seed"], "world", seat)
    count = ctx["regions"]
    ids = [f"region-{index:02d}" for index in range(count)]
    graph = {rid: set() for rid in ids}
    def link(a, b):
        graph[a].add(b)
        graph[b].add(a)
    for index in range(1, count):
        link(ids[index], ids[rng.randrange(index)])
    agency = ctx["axes"].get("agency", .5)
    risk = ctx["axes"].get("risk", .5)
    candidates = [(a,b) for i,a in enumerate(ids) for b in ids[i+1:] if b not in graph[a]]
    rng.shuffle(candidates)
    for a,b in candidates[:int(count * agency)]:
        link(a,b)
    travel = distances(graph, ids[0])
    exit_id = max(ids[1:], key=lambda rid: (travel[rid], rid))
    biomes = ("ruins", "harbor", "grove", "ridge", "cavern", "outpost")
    regions = [{"id": rid, "biome": rng.choice(biomes),
                "threat": min(100, int(15 + risk*35 + travel[rid]*8 + rng.randrange(10))),
                "reward": 10 + travel[rid]*12 + rng.randrange(8)}
               for rid in ids]
    world = {"regions":regions, "edges":[[a,b] for a in ids for b in sorted(graph[a]) if a < b],
             "entry":ids[0], "exit":exit_id,
             "diameter":max(max(distances(graph,r).values()) for r in ids)}
    validate_world(world)
    return world


def path_between(graph, start, goal):
    seen = {start: None}
    queue = deque([start])
    while queue:
        current=queue.popleft()
        if current == goal:
            path=[]
            while current is not None:
                path.append(current)
                current=seen[current]
            return list(reversed(path))
        for nxt in sorted(graph[current]):
            if nxt not in seen:
                seen[nxt]=current
                queue.append(nxt)
    raise ValueError("unreachable quest target")


def build_quest(ctx, seat, world):
    graph = validate_world(world)
    rng = seeded(ctx["seed"], "narrative", seat)
    # Quest steps follow a traversable regional walk rather than arbitrary IDs.
    route = path_between(graph, world["entry"], world["exit"])
    while len(route) < ctx["quest_depth"]:
        route.append(rng.choice(sorted(graph[route[-1]])))
    route = route[:ctx["quest_depth"]]
    objectives = ("survey", "recover", "escort", "repair", "deliver", "defend")
    steps=[]
    for index, rid in enumerate(route):
        steps.append({"id":f"quest-{index:02d}", "region":rid,
                      "objective":rng.choice(objectives), "required":index % 3 != 1 or index in (0,len(route)-1),
                      "next":[f"quest-{index+1:02d}"] if index+1<len(route) else []})
    return {"world_digest":digest(world), "steps":steps, "entry":steps[0]["id"],
            "ending":steps[-1]["id"], "route":route}


def validate_quest(quest, world):
    graph = validate_world(world)
    if quest.get("world_digest") != digest(world):
        raise ValueError("quest references a different world")
    route, steps = quest["route"], quest["steps"]
    if not 2 <= len(route) == len(steps) <= 24:
        raise ValueError("invalid quest inventory")
    if route[0] != world["entry"] or any(b not in graph[a] for a,b in zip(route,route[1:])):
        raise ValueError("quest route is not traversable")
    for index, step in enumerate(steps):
        if (step["region"] != route[index] or step["id"] != f"quest-{index:02d}"
                or step["next"] != ([f"quest-{index+1:02d}"] if index+1 < len(steps) else [])):
            raise ValueError("quest progression mismatch")
    if quest["entry"] != steps[0]["id"] or quest["ending"] != steps[-1]["id"]:
        raise ValueError("quest endpoints mismatch")
