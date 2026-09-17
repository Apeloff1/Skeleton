"""Wave-4 name tables."""
from __future__ import annotations
WEATHER = tuple(f"wx_{i:02d}" for i in range(40))
LOCKS = tuple(f"lock_{i:02d}" for i in range(36))
SOURCES = tuple(f"src_{i:02d}" for i in range(32))
ROUTES = tuple(f"route_{i:02d}" for i in range(30))
CRAFT = tuple(f"step_{i:02d}" for i in range(28))
QUESTS = tuple(f"q_{i:02d}" for i in range(28))
STATUS = (
    "frost","scald","sting","numb","glowburn","soot","oil","static","pulse","throb",
    "ache","itch","haze","blur","ring","whine","clench","slack","brittle","tacky",
    "slick","grit","film","crust","rift","seam","knot","fray",
)
VERBS = (
    "peek","probe","brace","duck","climb","drop","toss","catch","bind","cut",
    "stitch","smear","wipe","tap","knock","shove","yield","hold","aim","feint",
    "flank","cover","signal","recall",
)

def counts() -> dict[str, int]:
    return {
        "weather": len(WEATHER), "locks": len(LOCKS), "sources": len(SOURCES),
        "routes": len(ROUTES), "craft": len(CRAFT), "quests": len(QUESTS),
        "status": len(STATUS), "verbs": len(VERBS), "stored_prose": 0,
    }
