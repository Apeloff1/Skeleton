"""Extract explicit gameplay dependency relations from source passages.

Only concrete relation statements are admitted, not generic co-occurrences.
A relationship is candidate evidence until multiple distinct content revisions
corroborate it. The game compiler applies only relations among its supported,
non-executable mechanic vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .game_knowledge_acquisition import KnowledgePassage

_MECHANICS = (
    "double_jump","enemy_ai","collectible","checkpoint","inventory",
    "movement","collision","jump","dash","camera","combat",
    "puzzle","platform",
)
_LOOKUP = {
    "double jump":"double_jump",
    "enemy ai":"enemy_ai",
    "physics":"collision",
    "platforming":"jump",
    "item pickup":"collectible",
}
_VOCAB = set(_MECHANICS)|set(_LOOKUP)
_PATTERN = re.compile(
    r"\b("+"|".join(re.escape(x) for x in
        sorted(_VOCAB,key=len,reverse=True))+
    r")\b\s+(?:requires?|depends? on|needs?|must use)\s+"
    r"\b("+"|".join(re.escape(x) for x in
        sorted(_VOCAB,key=len,reverse=True))+
    r")\b",re.I,
)


@dataclass(frozen=True)
class MechanicRelation:
    passage_id: str
    dependency_of: str
    required_mechanic: str
    source_content_hash: str
    source_url: str
    start: int
    end: int


def extract_mechanic_dependencies(
    passages: tuple[KnowledgePassage,...],
    *, limit: int = 2000,
) -> tuple[MechanicRelation,...]:
    if not 1<=limit<=10000:
        raise ValueError("invalid game relation budget")
    collected:dict[tuple[str,str,str],MechanicRelation]={}
    for passage in passages:
        for m in _PATTERN.finditer(passage.text):
            left=_LOOKUP.get(m.group(1).casefold(),m.group(1).casefold().replace(" ","_"))
            right=_LOOKUP.get(m.group(2).casefold(),m.group(2).casefold().replace(" ","_"))
            if left == right or left not in _MECHANICS or right not in _MECHANICS:
                continue
            key=passage.passage_id,left,right
            collected[key]=MechanicRelation(
                passage.passage_id,left,right,passage.content_hash,
                passage.source_url,passage.start+m.start(),passage.start+m.end(),
            )
            if len(collected)>=limit:
                return tuple(collected.values())
    return tuple(collected.values())
