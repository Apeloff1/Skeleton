"""Bounded original living ecosystem with species dynamics and conservation.

Actual populations, food webs, water, predation, seasons, disease, migration and
habitat capacity change on each simulated turn. Up to 80 species are resident
in detail; the remaining authored species contribute bounded cohort aggregates.
No false claim of trained biology, native hardware validation or scientific model.
"""
from __future__ import annotations

ACTIONS=("north","south","east","west","inspect","observe","survey",
         "plant","water","restore","protect","treat","corridor",
         "feed","reintroduce","wait","checkpoint","retire")+tuple(
             "focus:"+str(i) for i in range(80))
MOVES={"north":(0,1),"south":(0,-1),"east":(1,0),"west":(-1,0)}
HABITATS=("woodland","wetland","grassland","highlands")
GUILDS=("producer","grazer","forager","predator")


class EcosystemActionError(ValueError):
    """Invalid original habitat, exhausted conservation resource or false proof."""


def _int(v,lo,hi,label):
    if type(v) is not int or not lo<=v<=hi:
        raise EcosystemActionError("invalid source ecology "+label)
    return v


def default_layout(config,seed):
    _int(seed,0,2**31-1,"seed")
    return {
        "title":"Original Living Biosphere "+str(seed%1000),
        "origin":[0,0],
        "habitats":[
            {"id":i,"kind":HABITATS[i],"site":[i%2,i//2],
             "capacity":config["food_capacity"]//4}
            for i in range(4)
        ],
        "critical_sites":[0,3],
        "season":("spring","summer","autumn","winter")[seed%4],
        "food_web_seed":seed,
        "nonterminal":True,
    }


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={
        "title","origin","habitats","critical_sites","season",
        "food_web_seed","nonterminal"
    }:
        raise EcosystemActionError("reviewed ecosystem requires exact scene structure")
    label=layout["title"]
    if type(label) is not str or not 3<=len(label)<=64 or not all(
        c.isalnum() or c in " _-" for c in label
    ):
        raise EcosystemActionError("unsafe original habitat title")
    if type(layout["origin"]) is not list or layout["origin"]!=[0,0]:
        raise EcosystemActionError("conservation survey must start at authored station")
    if type(layout["habitats"]) is not list or len(layout["habitats"])!=4:
        raise EcosystemActionError("four original ecological sites required")
    habitats=[]
    for i,h in enumerate(layout["habitats"]):
        if type(h) is not dict or set(h)!={"id","kind","site","capacity"}:
            raise EcosystemActionError("habitat needs exact identity, geology and site")
        if type(h["id"]) is not int or h["id"]!=i or h["kind"]!=HABITATS[i]:
            raise EcosystemActionError("source habitat identities cannot be swapped")
        site=[i%2,i//2]
        if type(h["site"]) is not list or h["site"]!=site:
            raise EcosystemActionError("ecological site cannot teleport on world map")
        capacity=_int(h["capacity"],0,config["food_capacity"],"habitat capacity")
        if capacity!=config["food_capacity"]//4:
            raise EcosystemActionError("habitat cannot mint ecological capacity")
        habitats.append({"id":i,"kind":HABITATS[i],"site":site,"capacity":capacity})
    if type(layout["critical_sites"]) is not list or (
        layout["critical_sites"]!=[0,3]
    ):
        raise EcosystemActionError("independent original survey sites must be preserved")
    if type(layout["season"]) is not str or layout["season"] not in (
        "spring","summer","autumn","winter"
    ):
        raise EcosystemActionError("unknown biome season")
    if type(layout["food_web_seed"]) is not int or not (
        0<=layout["food_web_seed"]<=2**31-1
    ):
        raise EcosystemActionError("exact integer authored food web seed required")
    if layout["nonterminal"] is not True:
        raise EcosystemActionError("living ecology must remain playable after conservation")
    return {
        "title":label,"origin":[0,0],"habitats":habitats,
        "critical_sites":[0,3],"season":layout["season"],
        "food_web_seed":layout["food_web_seed"],"nonterminal":True,
    }


def start(config,seed):
    source=normalize_layout(config,default_layout(config,seed))
    count=min(config["species"],80)
    creatures=[]
    for index in range(count):
        is_pred=index>=max(0,count-min(config["predators"],count))
        role=("predator" if is_pred else
              ("producer" if index%5==0 else
               "forager" if index%4==0 else "grazer"))
        creatures.append({
            "id":index,"guild":role,"habitat":(index+seed)%4,
            "population":config["initial_population"]+index%4,
            "health":100,"births":0,"deaths":0,
            "disease":0,"migrations":0,
        })
    return {
        "tick":0,"title":source["title"],"season":source["season"],
        "season_index":("spring","summer","autumn","winter").index(source["season"]),
        "position":[0,0],"habitats":[{**h,"food":h["capacity"]//2,
                                         "moisture":50,"protection":0,
                                         "health":75,"disease":0}
                                     for h in source["habitats"]],
        "species":creatures,"dormant_species":max(0,config["species"]-count),
        "dormant_population":max(0,config["species"]-count)*
                             config["initial_population"],
        "background_batches":0,"background_births":0,
        "background_deaths":0,"background_food_consumed":0,
        "species_total":config["species"],"predator_species":config["predators"],
        "food_web_seed":seed,
        "focus":0,
        "surveys":[],"interventions":0,"seed_bank":config["seed_bank"],
        "water":config["starting_water"],"medicine":config["medicine"],
        "credits":config["credits"],"corridors":[],
        "plantings":0,"treatments":0,"migration_events":0,
        "births":0,"deaths":0,"predation_events":0,
        "extinctions":0,"observations":[],"food_consumed":0,
        "conservation_checkpoint":False,"retired":False,
        "finished":False,"failed":False,"events":[],
    }


def apply_scene(state,config,layout):
    source=normalize_layout(config,layout)
    if state["tick"]!=0:
        raise EcosystemActionError("active ecosystem source cannot be rewritten")
    state["title"]=source["title"]
    state["position"]=list(source["origin"])
    state["season"]=source["season"]
    state["season_index"]=(
        "spring","summer","autumn","winter"
    ).index(source["season"])
    state["habitats"]=[{**h,"food":h["capacity"]//2,
                         "moisture":50,"protection":0,
                         "health":75,"disease":0} for h in source["habitats"]]
    state["food_web_seed"]=source["food_web_seed"]


def _here(state):
    x,y=state["position"]
    return state["habitats"][x+2*y]


def _spend(state,resource,amount):
    if state[resource]<amount:
        raise EcosystemActionError("ecological intervention requires finite "+resource)
    state[resource]-=amount


def _ecological_turn(state,config):
    season=state["season_index"]
    for habitat in state["habitats"]:
        # Seasonal primary production and conservation investments actually
        # replenish a finite shared food web; desert and winter regenerate less.
        yield_rate=max(0,config["food_regrowth"]+
                       (1 if habitat["health"]>=90 else 0)-
                       (2 if season==3 else 1 if season==1 else 0))
        if habitat["moisture"]<=config["drought_threshold"]:
            yield_rate//=2
        habitat["food"]=min(habitat["capacity"],
                            habitat["food"]+yield_rate)
        habitat["moisture"]=max(0,habitat["moisture"]-config["evaporation"])
        # Outbreaks are fully deterministic, observable, and treatable.
        if (habitat["kind"]=="wetland" and state["tick"]>0 and
            state["tick"]%config["outbreak_period"]==0):
            habitat["disease"]=min(100,habitat["disease"]+config["infection_rate"])
        if habitat["protection"]>0:habitat["protection"]-=1
    for species in state["species"]:
        habitat=state["habitats"][species["habitat"]]
        number=species["population"]
        if number<=0:continue
        if species["guild"]=="producer":
            # Population of producers relies on moisture but not consuming
            # the exact food stock used by animals.
            births=1 if habitat["moisture"]>=config["drought_threshold"] else 0
            losses=1 if habitat["moisture"]<config["drought_threshold"]//2 else 0
        else:
            need=max(1,number//config["individuals_per_food"])
            consumed=min(need,habitat["food"])
            habitat["food"]-=consumed
            state["food_consumed"]+=consumed
            hunger=need-consumed
            births=(1 if consumed==need and number<config["carrying_capacity"]
                    and state["tick"]%config["reproduction_period"]==0 else 0)
            losses=hunger
            if species["guild"]=="predator":
                prey=next((p for p in state["species"] if p["habitat"]==species["habitat"]
                           and p["guild"] in ("grazer","forager") and
                           p["population"]>0),None)
                if prey and state["tick"]%config["hunt_period"]==0:
                    killed=min(prey["population"],max(
                        0,config["predation_rate"]-
                        (config["protection_strength"] if habitat["protection"]>0 else 0)
                    ))
                    prey["population"]-=killed
                    prey["deaths"]+=killed
                    state["deaths"]+=killed
                    if prey["population"]==0 and killed>0:state["extinctions"]+=1
                    if killed>0:state["predation_events"]+=1
                    losses=max(0,losses-1)
        if habitat["disease"]>0:
            losses+=min(number,habitat["disease"]//config["disease_resistance"])
        losses=min(number,losses)
        updated=min(config["carrying_capacity"],number-losses+births)
        species["population"]=updated
        species["births"]+=births
        species["deaths"]+=losses
        state["births"]+=births
        state["deaths"]+=losses
        if updated==0:state["extinctions"]+=1
    # More than 80 authored species remain a bounded food-consuming cohort,
    # rather than a decorative untracked count. No one-per-animal allocation.
    if (state["dormant_species"]>0 and
        state["tick"]%config["cohort_period"]==0):
        state["background_batches"]+=1
        need=max(1,state["dormant_population"]//config["cohort_food_divisor"])
        available=sum(h["food"] for h in state["habitats"])
        consumed=min(need,available)
        balance=consumed
        for h in state["habitats"]:
            take=min(balance,h["food"])
            h["food"]-=take
            balance-=take
            if balance==0:break
        shortage=need-consumed
        lost=min(state["dormant_population"],shortage)
        birth=1 if lost==0 and state["dormant_population"]>0 and (
            state["dormant_population"]<
            state["dormant_species"]*config["carrying_capacity"]
        ) else 0
        state["dormant_population"]+=birth-lost
        state["background_births"]+=birth
        state["background_deaths"]+=lost
        state["background_food_consumed"]+=consumed
        state["food_consumed"]+=consumed
        state["births"]+=birth
        state["deaths"]+=lost
    if config["migration"] and state["tick"]%config["migration_period"]==0:
        # A true migration moves population (no cloning), within a reviewed
        # habitat corridor or through a paid spatial ecological crossing.
        for species in state["species"]:
            if species["population"]<=1:continue
            destination=(species["habitat"]+1)%4
            allowed=(
                config["natural_corridors"] or
                [species["habitat"],destination] in state["corridors"]
            )
            if not allowed:continue
            species["habitat"]=destination
            species["migrations"]+=1
            state["migration_events"]+=1
    if state["tick"]%config["season_ticks"]==0:
        state["season_index"]=(state["season_index"]+1)%4
        state["season"]=("spring","summer","autumn","winter")[
            state["season_index"]
        ]


def step(state,config,action):
    if action not in ACTIONS:
        raise EcosystemActionError("unknown original ecology command")
    if state["finished"] or state["failed"]:
        raise EcosystemActionError("terminated ecology cannot receive new actions")
    events=[]
    habitat=_here(state)
    if action in MOVES:
        dx,dy=MOVES[action]
        pos=[state["position"][0]+dx,state["position"][1]+dy]
        if 0<=pos[0]<=1 and 0<=pos[1]<=1:
            state["position"]=pos
            events.append("real_ecological_habitat_travel")
        else:events.append("bounded_ecology_world_edge")
    elif action.startswith("focus:"):
        who=int(action.split(":")[1])
        if who>=len(state["species"]):
            raise EcosystemActionError("cannot focus on nonresident species")
        state["focus"]=who
        events.append("authored_species_selected")
    elif action=="observe":
        subject=state["species"][state["focus"]]
        if subject["habitat"]!=habitat["id"]:
            raise EcosystemActionError("observations must occur at actual wildlife habitat")
        entry={"tick":state["tick"],"species":subject["id"],
               "population":subject["population"],"habitat":habitat["id"]}
        state["observations"].append(entry)
        if len(state["observations"])>config["observation_budget"]:
            state["observations"]=state["observations"][-config["observation_budget"]:]
        events.append("direct_original_species_observation")
    elif action=="survey":
        if habitat["id"] in state["surveys"]:
            raise EcosystemActionError("one physical habitat survey earns one finding")
        state["surveys"].append(habitat["id"])
        state["surveys"].sort()
        events.append("verified_original_habitat_survey")
    elif action=="plant":
        _spend(state,"seed_bank",config["seed_cost"])
        habitat["food"]=min(habitat["capacity"],
                            habitat["food"]+config["plant_food"])
        state["plantings"]+=1
        state["interventions"]+=1
        events.append("finite_seed_bank_rewilding")
    elif action=="water":
        _spend(state,"water",config["water_cost"])
        habitat["moisture"]=min(100,habitat["moisture"]+config["watering_gain"])
        state["interventions"]+=1
        events.append("finite_habitat_water_restoration")
    elif action=="restore":
        _spend(state,"credits",config["restoration_cost"])
        habitat["health"]=min(100,habitat["health"]+config["restoration_heal"])
        habitat["disease"]=max(0,habitat["disease"]-config["restoration_heal"])
        state["interventions"]+=1
        events.append("financed_biome_restoration")
    elif action=="protect":
        _spend(state,"credits",config["protection_cost"])
        habitat["protection"]=config["protection_ticks"]
        state["interventions"]+=1
        events.append("temporary_source_bound_habitat_protection")
    elif action=="treat":
        if habitat["disease"]==0:
            raise EcosystemActionError("medicine requires a real detected outbreak")
        _spend(state,"medicine",1)
        habitat["disease"]=max(0,habitat["disease"]-config["treatment_strength"])
        state["treatments"]+=1
        events.append("finite_wildlife_disease_treatment")
    elif action=="corridor":
        dest=(habitat["id"]+1)%4
        if [habitat["id"],dest] in state["corridors"]:
            raise EcosystemActionError("cannot duplicate an already paid migration corridor")
        _spend(state,"credits",config["corridor_cost"])
        state["corridors"].append([habitat["id"],dest])
        state["interventions"]+=1
        events.append("paid_original_habitat_connection")
    elif action=="feed":
        _spend(state,"credits",config["feed_cost"])
        habitat["food"]=min(habitat["capacity"],
                            habitat["food"]+config["feed_units"])
        state["interventions"]+=1
        events.append("finite_ecological_food_restocking")
    elif action=="reintroduce":
        subject=state["species"][state["focus"]]
        if subject["population"]>0 or habitat["id"]!=subject["habitat"]:
            raise EcosystemActionError("reintroduction requires an actually extinct local species")
        if habitat["food"]<config["reintroduction_food"]:
            raise EcosystemActionError("habitat cannot host reintroduced wildlife")
        _spend(state,"credits",config["reintroduction_cost"])
        habitat["food"]-=config["reintroduction_food"]
        subject["population"]=config["reintroduction_population"]
        state["extinctions"]=max(0,state["extinctions"]-1)
        state["interventions"]+=1
        events.append("resource_backed_species_reintroduction")
    elif action=="checkpoint":
        if (state["conservation_checkpoint"] or
            any(i not in state["surveys"] for i in (0,3)) or
            state["interventions"]<config["minimum_interventions"] or
            sum(s["population"] for s in state["species"])<
            config["minimum_living_population"]):
            raise EcosystemActionError("earned conservation evidence and live population required")
        state["conservation_checkpoint"]=True
        events.append("nonterminal_original_biosphere_conservation_milestone")
    elif action=="retire":
        if not state["conservation_checkpoint"] or state["position"]!=[0,0]:
            raise EcosystemActionError("optional ecological retirement requires evidence and home")
        state["retired"]=state["finished"]=True
        events.append("voluntary_conservationist_retirement")
    state["tick"]+=1
    _ecological_turn(state,config)
    if state["tick"]>=config["turn_limit"]:
        state["failed"]=True
        events.append("bounded_ecosystem_rehearsal_expired")
    state["events"]=events
    return events
