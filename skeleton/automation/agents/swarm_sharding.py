"""Stable rendezvous hashing for distributing swarm ownership."""
from __future__ import annotations
from hashlib import blake2b

def _score(key:str,node:str)->int: return int.from_bytes(blake2b(f"{key}\0{node}".encode(),digest_size=8).digest(),"big")
def owners(key:str,nodes:list[str]|tuple[str,...],replicas:int=1)->tuple[str,...]:
 if replicas<1: raise ValueError("replicas must be positive")
 unique=tuple(dict.fromkeys(n for n in nodes if n))
 if not unique: return ()
 ranked=sorted(unique,key=lambda n:(-_score(key,n),n))
 return tuple(ranked[:min(replicas,len(ranked))])
def distribution(keys:list[str],nodes:list[str],replicas:int=1)->dict[str,int]:
 result={n:0 for n in dict.fromkeys(nodes)}
 for key in keys:
  for node in owners(key,nodes,replicas): result[node]=result.get(node,0)+1
 return result


# The legacy owner/distribution API remains unchanged. Weighted ownership
# and movement are separately opt-in, with a finite proposal work budget.
from dataclasses import dataclass
from hashlib import sha256
from math import log
from fractions import Fraction
import json


def _identity(value: str) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 256
            or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError("invalid shard identity")
    return value


def _natural(value: int, maximum: int = 10**12) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid shard quantity")
    return value


@dataclass(frozen=True, slots=True)
class ShardMember:
    node_id: str
    generation: int
    weight: int
    capacity_bytes: int
    occupied_bytes: int
    accepting: bool = True

    def __post_init__(self) -> None:
        _identity(self.node_id)
        _natural(self.generation)
        _natural(self.weight, 10000)
        _natural(self.capacity_bytes)
        _natural(self.occupied_bytes)
        if not self.weight or self.occupied_bytes > self.capacity_bytes or type(self.accepting) is not bool:
            raise ValueError("invalid shard member capacity")


@dataclass(frozen=True, slots=True)
class ResidentShard:
    shard_id: str
    tenant_id: str
    owner_id: str
    state_sha256: str
    bytes_used: int
    generation: int
    movable: bool

    def __post_init__(self) -> None:
        for value in (self.shard_id, self.tenant_id, self.owner_id):
            _identity(value)
        if (type(self.state_sha256) is not str or len(self.state_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.state_sha256)):
            raise ValueError("invalid shard state digest")
        if not _natural(self.bytes_used) or type(self.movable) is not bool:
            raise ValueError("invalid resident shard")
        _natural(self.generation)


def weighted_owners(key: str, members: tuple[ShardMember, ...], *, generation: int,
                    replicas: int = 1) -> tuple[str, ...]:
    """Weighted rendezvous via exponential race, independent of membership order.

    Weight is an explicit host policy, not a load measurement. The generation
    fences observations but is deliberately not hashed (unchanged memberships
    must retain their assignments).
    """
    _identity(key)
    _natural(generation)
    if type(replicas) is not int or not 1 <= replicas <= 256 or len(members) > 256:
        raise ValueError("invalid replica or membership ceiling")
    if any(not isinstance(m, ShardMember) or m.generation != generation for m in members):
        raise ValueError("mixed membership generations")
    if len({m.node_id for m in members}) != len(members):
        raise ValueError("duplicate shard member")
    def rank(member: ShardMember) -> tuple[float, str]:
        # Open interval from 52-bit integer; never log(0) or divide by zero.
        raw = _score(key, member.node_id) >> 12
        uniform = (raw + 0.5) / (1 << 52)
        return -log(uniform) / member.weight, member.node_id
    return tuple(m.node_id for m in sorted((m for m in members if m.accepting), key=rank)[:replicas])


@dataclass(frozen=True, slots=True)
class ShardMove:
    shard_id: str
    source: str
    target: str
    bytes_reserved: int
    state_sha256: str
    generation: int
    binding_sha256: str


@dataclass(frozen=True, slots=True)
class ShardRebalance:
    moves: tuple[ShardMove, ...]
    held: tuple[str, ...]
    reserved_bytes: int


def plan_resident_rebalance(shards: tuple[ResidentShard, ...], members: tuple[ShardMember, ...],
                            *, tenant_id: str, generation: int, max_moves: int = 64,
                            max_bytes: int = 1 << 30) -> ShardRebalance:
    """Bound membership change by actual resident bytes, not only key count.

    Destination capacity is reserved without crediting the source release.
    A host must fence the source, transfer and verify the exact shard state,
    publish ownership under its existing membership authority, then ack release.
    Unknown/active shards must be supplied as nonmovable. No move executes here.
    """
    _identity(tenant_id)
    _natural(generation)
    _natural(max_bytes)
    if not 1 <= _natural(max_moves, 1024) or len(shards) > 4096 or len(members) > 256:
        raise ValueError("invalid rebalance ceiling")
    if len(shards) * max(1, len(members)) > 1_048_576:
        raise ValueError("rebalance work ceiling")
    weighted_owners("validation", members, generation=generation)
    by_id = {m.node_id: m for m in members}
    if any(not isinstance(s, ResidentShard) or s.tenant_id != tenant_id
           or s.generation != generation or s.owner_id not in by_id for s in shards):
        raise ValueError("invalid shard scope")
    if len({s.shard_id for s in shards}) != len(shards):
        raise ValueError("duplicate resident shard")
    occupied = {m.node_id: 0 for m in members}
    for shard in shards:
        occupied[shard.owner_id] += shard.bytes_used
    if any(occupied[m.node_id] > m.occupied_bytes for m in members):
        raise ValueError("resident accounting exceeds member observation")
    room = {m.node_id: m.capacity_bytes - m.occupied_bytes for m in members}
    moves, held = [], []
    spent = 0
    for shard in sorted(shards, key=lambda s: (by_id[s.owner_id].accepting, -s.bytes_used, s.shard_id)):
        ranked = weighted_owners(tenant_id + ":" + shard.shard_id if len(tenant_id)+len(shard.shard_id)<255
                                 else sha256(json.dumps([tenant_id,shard.shard_id]).encode()).hexdigest(),
                                 members, generation=generation, replicas=max(1,len(members)))
        if ranked and ranked[0] == shard.owner_id:
            continue
        if not shard.movable or len(moves) >= max_moves or spent + shard.bytes_used > max_bytes:
            held.append(shard.shard_id)
            continue
        target = None
        for node in ranked:
            if node == shard.owner_id:
                break
            if room[node] >= shard.bytes_used:
                target = node
                break
        if target is None:
            held.append(shard.shard_id)
            continue
        pin = sha256(json.dumps(["resident-rebalance-v1", tenant_id, generation,
                    shard.shard_id, shard.owner_id, target, shard.state_sha256,
                    shard.bytes_used, room[target]], separators=(",", ":")).encode()).hexdigest()
        moves.append(ShardMove(shard.shard_id,shard.owner_id,target,shard.bytes_used,
                               shard.state_sha256,generation,pin))
        room[target] -= shard.bytes_used
        spent += shard.bytes_used
    return ShardRebalance(tuple(moves),tuple(sorted(held)),spent)
