"""Route-body signature admission for local authored game navigation.

The legacy design-note API remains compatible; this strict adapter
requires the note body itself to equal the canonical route authorization
(including plan, geometry, direction and consumer). Signer key custody
is external; this module never publishes or invents an approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from skeleton.app.recovered_evidence import (
    EvidenceError, array, fields, identifier, integer, text, digest, canonical, pin, HEX,
)
from skeleton.frontier_nav.route_grounding import (
    CONSUMERS, DesignNote, ApprovedRoute, RouteGrounder, hmac_verifier,
)

MAX_ROUTES=128
MAX_WAYPOINTS=64
MAX_ROUTE_HOPS=4096
MAX_LOCATIONS=256
MAX_COORDINATE=1_000_000_000


def coordinates(raw,world):
    if type(raw) is not dict or set(raw)!=set(world.edges) or not 1<=len(raw)<=MAX_LOCATIONS:
        raise EvidenceError("coordinate catalogue must bind the entire authored world")
    return {name:tuple(integer(v,-MAX_COORDINATE,MAX_COORDINATE)
                       for v in array(raw[name],3,3)) for name in sorted(raw)}


def route_body(row,*,plan_digest,geometry_digest):
    """The exact bytes a separate local approval authority must sign."""
    fields(row,{"route_id","waypoints","consumers","bidirectional","note_id"})
    rid=identifier(row["route_id"])
    points=tuple(identifier(x) for x in array(row["waypoints"],2,MAX_WAYPOINTS))
    if len(set(points))!=len(points):
        raise EvidenceError("repeated waypoint in approval")
    consumers=tuple(sorted(identifier(x) for x in array(row["consumers"],1,len(CONSUMERS))))
    if len(set(consumers))!=len(consumers) or not set(consumers)<=CONSUMERS:
        raise EvidenceError("invalid route consumer scope")
    if type(row["bidirectional"]) is not bool:
        raise EvidenceError("route direction must be explicit")
    identifier(row["note_id"])
    return {"schema":"skeleton.route-approval.v1","route_id":rid,"waypoints":list(points),
            "consumers":list(consumers),"bidirectional":row["bidirectional"],
            "plan_digest":plan_digest,"geometry_digest":geometry_digest}


@dataclass(frozen=True)
class ApprovedNavigation:
    grounder: RouteGrounder
    locations: object
    approval_digest: str
    geometry_digest: str
    routes: int


def load_approvals(raw,*,world,plan_digest,expected_digest,key):
    if type(key) is not bytes or not 32<=len(key)<=128:
        raise EvidenceError("independent local route approval key required")
    fields(raw,{"schema","coordinates","routes","plan_digest"})
    if raw["schema"]!="skeleton.signed-navigation.order.v1":
        raise EvidenceError("unsupported route catalogue")
    pin(digest(raw),expected_digest)
    pin(raw["plan_digest"],plan_digest)
    positions=coordinates(raw["coordinates"],world)
    geometry_digest=digest(raw["coordinates"])
    grounder=RouteGrounder(hmac_verifier(key))
    notes=set()
    hops=0
    for entry in array(raw["routes"],1,MAX_ROUTES):
        fields(entry,{"route_id","waypoints","consumers","bidirectional","note_id","signature"})
        signed={k:v for k,v in entry.items() if k!="signature"}
        body=route_body(signed,plan_digest=plan_digest,geometry_digest=geometry_digest)
        signature=entry["signature"]
        if type(signature) is not str or not HEX.fullmatch(signature):
            raise EvidenceError("invalid route signature encoding")
        note_id=signed["note_id"]
        if note_id in notes:
            raise EvidenceError("design-note id reused")
        notes.add(note_id)
        points=tuple(body["waypoints"])
        if any(point not in positions for point in points):
            raise EvidenceError("signed route references unknown location")
        for source,dest in zip(points,points[1:]):
            if dest not in world.edges[source]:
                raise EvidenceError("signed route outside authored directed world")
            if body["bidirectional"] and source not in world.edges[dest]:
                raise EvidenceError("reverse route outside authored directed world")
        hops+=len(points)-1
        if hops>MAX_ROUTE_HOPS:
            raise EvidenceError("signed route hop ceiling")
        note=DesignNote(note_id,canonical(body).decode("ascii"),signature)
        grounder.approve(ApprovedRoute(body["route_id"],points,note,
                                      frozenset(body["consumers"]),body["bidirectional"]))
    return ApprovedNavigation(grounder,MappingProxyType(positions),expected_digest,
                              geometry_digest,len(notes))
