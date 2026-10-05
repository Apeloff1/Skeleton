"""Stable SDK and data contracts VOL-342..348."""
from dataclasses import dataclass
from enum import Enum
from .contracts import sha256_json
@dataclass(frozen=True,slots=True)
class SDKExport: name:str; contract_version:str; deprecated:bool=False
@dataclass(frozen=True,slots=True)
class SDKCompatibility: source_version:str; target_version:str; compatible:bool
@dataclass(frozen=True,slots=True)
class InternalSDK: version:str; exports:tuple[SDKExport,...]
def supported_export(sdk,name):
 if not sdk.version or not name or len({x.name for x in sdk.exports})!=len(sdk.exports) or any(not x.name or not x.contract_version for x in sdk.exports):raise ValueError("invalid SDK export identity")
 return next((x for x in sdk.exports if x.name==name and not x.deprecated),None)
@dataclass(frozen=True,slots=True)
class ProviderAdapterSpec: provider:str; version:str; capabilities:frozenset[str]
@dataclass(frozen=True,slots=True)
class ProviderConformance: canonical_input:bool; canonical_output:bool; native_leak:bool
@dataclass(frozen=True,slots=True)
class ProviderSDK: adapters:tuple[ProviderAdapterSpec,...]
def provider_conformant(c):return c.canonical_input and c.canonical_output and not c.native_leak
class StateClass(str,Enum): DURABLE="durable"; EPHEMERAL="ephemeral"; BLOB="blob"
class Consistency(str,Enum): STRONG="strong"; EVENTUAL="eventual"
@dataclass(frozen=True,slots=True)
class StoreHandle: store_id:str; state_class:StateClass; consistency:Consistency; transactions:bool; idempotency:bool; migrations:bool
@dataclass(frozen=True,slots=True)
class TransactionHandle: store_id:str; transaction_id:str
@dataclass(frozen=True,slots=True)
class StorageSDK: stores:tuple[StoreHandle,...]
def select_store(sdk,state_class,consistency):
 if len({s.store_id for s in sdk.stores})!=len(sdk.stores) or any(not s.store_id for s in sdk.stores):raise ValueError("unique storage identity required")
 xs=[s for s in sdk.stores if s.state_class is state_class and s.consistency is consistency]
 if len(xs)!=1:raise ValueError("storage requirement unresolved")
 return xs[0]
@dataclass(frozen=True,slots=True)
class EventPublisher: publisher_id:str; envelope_version:str
@dataclass(frozen=True,slots=True)
class EventConsumer: consumer_id:str; envelope_version:str; replay:bool; idempotency:bool
@dataclass(frozen=True,slots=True)
class EventSDK: version:str; publishers:tuple[EventPublisher,...]; consumers:tuple[EventConsumer,...]
def event_compatible(p,c):return all((p.publisher_id,p.envelope_version,c.consumer_id,c.envelope_version)) and p.envelope_version==c.envelope_version and c.idempotency and c.replay
@dataclass(frozen=True,slots=True)
class Scorer: name:str; version:str; inputs:tuple[str,...]; outputs:tuple[str,...]; dependencies:tuple[str,...]
@dataclass(frozen=True,slots=True)
class EvaluationResult: scorer:str; scorer_version:str; environment_id:str; model_id:str; config_digest:str; score:float
@dataclass(frozen=True,slots=True)
class EvaluationSDK: environment_id:str; model_id:str; config:dict
def record_evaluation(sdk,scorer,score):
 if not all((sdk.environment_id,sdk.model_id,scorer.name,scorer.version)) or not scorer.inputs or not scorer.outputs:raise ValueError("complete evaluation identity required")
 return EvaluationResult(scorer.name,scorer.version,sdk.environment_id,sdk.model_id,sha256_json(sdk.config),score)
@dataclass(frozen=True,slots=True)
class BenchmarkManifest: plugin_version:str; dataset_id:str; dataset_version:str; required_resources:tuple[str,...]
@dataclass(frozen=True,slots=True)
class BenchmarkPlugin: name:str; manifest:BenchmarkManifest
@dataclass(frozen=True,slots=True)
class BenchmarkExecution: plugin:str; plugin_version:str; dataset_id:str; dataset_version:str; admitted:bool
def admit_benchmark(p,*,dataset_rights,security_allowed,resources_allowed):
 m=p.manifest
 if not all((p.name,m.plugin_version,m.dataset_id,m.dataset_version)) or any(not r for r in m.required_resources):raise ValueError("complete benchmark identity required")
 ok=dataset_rights and security_allowed and resources_allowed
 return BenchmarkExecution(p.name,m.plugin_version,m.dataset_id,m.dataset_version,ok)
@dataclass(frozen=True,slots=True)
class DataField: name:str; meaning:str; nullable:bool; unit:str|None; freshness:str; classification:str
@dataclass(frozen=True,slots=True)
class DataConsumer: consumer_id:str; contract_version:str
@dataclass(frozen=True,slots=True)
class DataContract: name:str; version:str; fields:tuple[DataField,...]; consumers:tuple[DataConsumer,...]
def breaking_change(old,new,*,migration_declared):
 oldf={f.name:f for f in old.fields};newf={f.name:f for f in new.fields}
 breaking=any(n not in newf or oldf[n]!=newf[n] for n in oldf)
 return breaking and not migration_declared
