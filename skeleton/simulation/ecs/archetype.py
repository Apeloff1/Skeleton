"""Archetype templates for deterministic entity construction."""
from __future__ import annotations
import copy
from dataclasses import dataclass
from typing import Any, Mapping
from .canonical import digest
from .errors import SchemaConflictError, ValidationError
from .store import EntityRecord, EntityStore
MAX_ARCHETYPES=4096;MAX_TEMPLATE_COMPONENTS=128
@dataclass(frozen=True)
class ComponentTemplate:
    schema_id:str;schema_version:int|None;data:Mapping[str,Any]
@dataclass(frozen=True)
class Archetype:
    archetype_id:str;components:tuple[ComponentTemplate,...];tags:tuple[str,...]=()
    def __post_init__(self):
        if not isinstance(self.archetype_id,str) or not self.archetype_id:raise ValidationError("archetype id required")
        comps=tuple(self.components)
        if len(comps)>MAX_TEMPLATE_COMPONENTS:raise ValidationError("too many archetype components")
        ids=[c.schema_id for c in comps]
        if len(ids)!=len(set(ids)):raise ValidationError("duplicate archetype components")
        object.__setattr__(self,"components",tuple(sorted(comps,key=lambda c:c.schema_id)));object.__setattr__(self,"tags",tuple(sorted(set(self.tags))))
    @property
    def fingerprint(self):return digest({"id":self.archetype_id,"components":[(c.schema_id,c.schema_version,dict(c.data)) for c in self.components],"tags":self.tags})
class ArchetypeRegistry:
    def __init__(self):self._items={}
    def register(self,archetype:Archetype):
        if len(self._items)>=MAX_ARCHETYPES and archetype.archetype_id not in self._items:raise ValidationError("archetype bound exceeded")
        prior=self._items.get(archetype.archetype_id)
        if prior and prior.fingerprint!=archetype.fingerprint:raise SchemaConflictError("archetype id conflict")
        self._items[archetype.archetype_id]=archetype;return archetype
    def get(self,archetype_id):
        try:return self._items[archetype_id]
        except KeyError as exc:raise ValidationError("archetype not found",context={"archetype_id":archetype_id}) from exc
    def ids(self):return tuple(sorted(self._items))
    def spawn(self,store:EntityStore,archetype_id:str,*,entity_id:str|None=None,hint:str|None=None,overrides:Mapping[str,Mapping[str,Any]]|None=None)->EntityRecord:
        archetype=self.get(archetype_id);overrides=overrides or {}
        with store.transaction():
            record=store.create_entity(entity_id,hint=hint or archetype_id)
            for template in archetype.components:
                data=copy.deepcopy(dict(template.data));data.update(copy.deepcopy(dict(overrides.get(template.schema_id,{}))))
                store.set_component(record.entity_id,template.schema_id,data,version=template.schema_version)
            return store.get_entity(record.entity_id)
