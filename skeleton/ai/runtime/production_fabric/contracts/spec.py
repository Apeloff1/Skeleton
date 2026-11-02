"""Strict world, scene, choice and ending schemas for deterministic playable games."""
from dataclasses import dataclass
from typing import Any
from .canonical import dumps
from .errors import ContractError
from .identity import identifier

@dataclass(frozen=True)
class Choice:
    id: str
    text: str
    destination: str
    requires: tuple[str, ...]
    grants: tuple[str, ...]
    costs: tuple[str, ...]

@dataclass(frozen=True)
class Scene:
    id: str
    title: str
    description: str
    choices: tuple[Choice, ...]
    tags: tuple[str, ...]

@dataclass(frozen=True)
class World:
    id: str
    title: str
    start: str
    scenes: dict[str, Scene]
    endings: tuple[str, ...]
    provenance: str

def _strings(value: Any, *, maximum: int=64) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ContractError('expected bounded string list')
    result = tuple((identifier(s) for s in value))
    if len(set(result)) != len(result):
        raise ContractError('duplicate identifiers')
    return result

def _text(value: Any, *, max_len: int=8192) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len or any((ord(c) < 32 and c not in '\n\t' for c in value)):
        raise ContractError('invalid text')
    return value

def parse_world(value: dict[str, Any]) -> World:
    if not isinstance(value, dict) or set(value) != {'id', 'title', 'start', 'scenes', 'endings', 'provenance'}:
        raise ContractError('world fields must match the exact v1 schema')
    dumps(value)
    world_id = identifier(value['id'])
    title = _text(value['title'], max_len=256)
    start = identifier(value['start'])
    provenance = _text(value['provenance'], max_len=256)
    raw_scenes = value['scenes']
    if not isinstance(raw_scenes, list) or not 1 <= len(raw_scenes) <= 512:
        raise ContractError('world must contain 1..512 scenes')
    scenes: dict[str, Scene] = {}
    choice_ids = set()
    for item in raw_scenes:
        if not isinstance(item, dict) or set(item) != {'id', 'title', 'description', 'choices', 'tags'}:
            raise ContractError('invalid scene fields')
        sid = identifier(item['id'])
        if sid in scenes:
            raise ContractError('duplicate scene')
        choices = []
        raw = item['choices']
        if not isinstance(raw, list) or len(raw) > 32:
            raise ContractError('unbounded scene choices')
        for ch in raw:
            if not isinstance(ch, dict) or set(ch) != {'id', 'text', 'destination', 'requires', 'grants', 'costs'}:
                raise ContractError('invalid choice fields')
            choice = Choice(identifier(ch['id']), _text(ch['text'], max_len=512), identifier(ch['destination']), _strings(ch['requires']), _strings(ch['grants']), _strings(ch['costs']))
            if choice.id in choice_ids:
                raise ContractError('choice IDs must be unique per world')
            choice_ids.add(choice.id)
            if set(choice.grants) & set(choice.costs):
                raise ContractError('choice cannot grant and cost same flag')
            choices.append(choice)
        scenes[sid] = Scene(sid, _text(item['title'], max_len=256), _text(item['description']), tuple(choices), _strings(item['tags']))
    ends = _strings(value['endings'])
    if not ends or start not in scenes or any((end not in scenes or scenes[end].choices for end in ends)):
        raise ContractError('invalid start or nonterminal ending')
    if any((ch.destination not in scenes for scene in scenes.values() for ch in scene.choices)):
        raise ContractError('dangling scene destination')
    return World(world_id, title, start, scenes, ends, provenance)

def to_data(world: World) -> dict[str, Any]:
    return {'id': world.id, 'title': world.title, 'start': world.start, 'provenance': world.provenance, 'endings': list(world.endings), 'scenes': [{'id': s.id, 'title': s.title, 'description': s.description, 'tags': list(s.tags), 'choices': [{'id': c.id, 'text': c.text, 'destination': c.destination, 'requires': list(c.requires), 'grants': list(c.grants), 'costs': list(c.costs)} for c in s.choices]} for s in world.scenes.values()]}
