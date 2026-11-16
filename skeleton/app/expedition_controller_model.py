"""Generate and independently pin an authored original expedition journey."""
from __future__ import annotations
from skeleton.app.recovered_evidence import EvidenceError,fields,identifier,integer,digest,seal,pin,HEX
from skeleton.jeeves.game_frontier_expedition import Traveler,ExpeditionEpisode,find_route
from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile,author_archipelago
from skeleton.app.expedition_controller_bridge import semantic_route


def source(raw):
    fields(raw,{"schema","project_id","seed","islands","gdd_digest","objective"})
    if raw["schema"]!="skeleton.expedition-controller-journey.order.v1":
        raise EvidenceError("unknown controller journey order")
    project=identifier(raw["project_id"])
    seed=integer(raw["seed"],0,2**63-1)
    islands=integer(raw["islands"],3,24)
    gdd=raw["gdd_digest"]
    if type(gdd) is not str or not HEX.fullmatch(gdd):
        raise EvidenceError("authored GDD digest required")
    world=author_archipelago(project,digest(raw),ArchipelagoProfile(seed=seed,islands=islands))
    player=Traveler(permitted_modes=frozenset(("walk","rope_bridge","updraft","glide","airship","portal","climb","dive","swim")),
                    flags=frozenset(("glider","airship_license","diving_gear","portal_key")),
                    equipment=frozenset(("instrument_navigation",)),max_stamina=1000,skill=.8)
    destination=world.destinations[0]
    route=find_route(world,player,destination,objective=raw["objective"],max_expansions=100_000)
    actions,journey=semantic_route(ExpeditionEpisode(world,player),route)
    if not actions:
        raise EvidenceError("empty original route")
    plan=seal({"schema":"skeleton.expedition-controller-journey.plan.v1",
               "order_digest":digest(raw),"world_digest":world.digest,"traveler_digest":journey.episode.traveler_digest,
               "route_digest":route.digest,"destination":destination,"edges":list(route.edge_ids),
               "semantic_actions":list(actions),"expected_snapshot_digest":journey.episode.snapshot()["snapshot_digest"],
               "semantic_state_chain":digest(journey.records)})
    return world,player,plan


def plan_journey(raw,*,authorized):
    if authorized is not True:
        raise PermissionError("explicit local controller operator required")
    return source(raw)[2]
