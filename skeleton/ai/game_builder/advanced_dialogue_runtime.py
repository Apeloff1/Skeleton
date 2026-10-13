"""Source-bound original dialogue, NPC memory, social consequences and evidence."""
from __future__ import annotations

TOPICS=("bridge","harvest")
ACTIONS=("inspect","wait","rest","leave","empathize","offer:aid","listen",
         "record","challenge","report","retire","ask:bridge","ask:harvest",
         "verify:bridge","verify:harvest")+tuple("approach:"+str(i) for i in range(8))

class DialogueActionError(ValueError):
    """Impossible, forged or unearned original conversation action."""

def default_layout(config,seed):
    if type(seed) is not int or not 0<=seed<=2**31-1:
        raise DialogueActionError("invalid original world seed")
    count=min(8,config["speakers"])
    claims=[]
    for i in range(count):
        topic=TOPICS[(i//2)%2]
        truth=i<4 or i%5!=0
        claim=("The eastern bridge was repaired." if topic=="bridge"
               else "The village orchard survived the storm.")
        if not truth:claim="The eastern bridge collapsed overnight."
        claims.append({"speaker":i,"topic":topic,"claim":claim,"truth":truth})
    return {"title":"Original Witness Village "+str(seed%1000),
            "venue":"civic_gathering","active_speakers":count,
            "statements":claims,"nonterminal":True}

def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={"title","venue","active_speakers","statements","nonterminal"}:
        raise DialogueActionError("exact original dialogue scene required")
    title=layout["title"]
    if type(title) is not str or not 3<=len(title)<=64 or not all(
        c.isalnum() or c in " _-.'" for c in title):
        raise DialogueActionError("unsafe original source title")
    if type(layout["venue"]) is not str or layout["venue"] not in (
        "civic_gathering","harbor","market","sanctuary"):
        raise DialogueActionError("unknown authored conversation venue")
    count=min(8,config["speakers"])
    if type(layout["active_speakers"]) is not int or layout["active_speakers"]!=count:
        raise DialogueActionError("source speaker budget differs from settings")
    if layout["nonterminal"] is not True:
        raise DialogueActionError("witness world must remain playable")
    rows=layout["statements"]
    if type(rows) is not list or len(rows)!=count:
        raise DialogueActionError("one reviewed statement per active NPC required")
    result=[]
    for i,row in enumerate(rows):
        if type(row) is not dict or set(row)!={"speaker","topic","claim","truth"}:
            raise DialogueActionError("malformed authored testimony")
        if type(row["speaker"]) is not int or row["speaker"]!=i:
            raise DialogueActionError("canonical resident identity required")
        if type(row["topic"]) is not str or row["topic"] not in TOPICS:
            raise DialogueActionError("unknown witnessed event")
        claim=row["claim"]
        if type(claim) is not str or not 10<=len(claim)<=100 or any(
            ord(ch)<32 or ord(ch)>126 or ch in "<>" for ch in claim):
            raise DialogueActionError("unapproved markup or source testimony")
        if type(row["truth"]) is not bool:
            raise DialogueActionError("fictional-world truth label must be boolean")
        result.append(dict(row))
    return {"title":title,"venue":layout["venue"],"active_speakers":count,
            "statements":result,"nonterminal":True}

def start(config,seed):
    source=normalize_layout(config,default_layout(config,seed))
    return {"title":source["title"],"venue":source["venue"],
            "statements":source["statements"],"speaker":None,
            "trust":[config["starting_trust"]]*source["active_speakers"],
            "energy":config["social_energy"],"favors":config["gift_tokens"],
            "turn":0,"asked_topic":None,"pending":None,"visits":[],
            "memory":[],"records":[],"verified_topics":[],
            "challenge_count":0,"dialogue_lines":0,"reputation":0,
            "report_count":0,"checkpoint":False,"finished":False,
            "failed":False,"events":[],
            "background_speakers":config["speakers"]-source["active_speakers"]}

def apply_scene(state,config,layout):
    if state["turn"]!=0:
        raise DialogueActionError("live testimony cannot be replaced")
    source=normalize_layout(config,layout)
    state["title"]=source["title"];state["venue"]=source["venue"]
    state["statements"]=source["statements"]

def _spend(state,amount):
    if state["energy"]<amount:
        raise DialogueActionError("conversation requires finite energy")
    state["energy"]-=amount

def _memory(state,config,event):
    if config["memory_turns"]==0:
        state["memory"]=[]
        return
    state["memory"].append({"turn":state["turn"],"speaker":state["speaker"],
                            "event":event})
    state["memory"]=[m for m in state["memory"]
                     if state["turn"]-m["turn"]<config["memory_turns"]]
    state["memory"]=state["memory"][-config["memory_capacity"]:]

def step(state,config,action):
    if action not in ACTIONS:
        raise DialogueActionError("unknown social gameplay command")
    if state["finished"] or state["failed"]:
        raise DialogueActionError("terminated dialogue cannot advance")
    who=state["speaker"]
    events=[]
    if action.startswith("approach:"):
        target=int(action.split(":")[1])
        if target>=len(state["trust"]):
            raise DialogueActionError("inactive original NPC cannot speak")
        _spend(state,config["conversation_cost"])
        state["speaker"]=target
        state["asked_topic"]=state["pending"]=None
        if target not in state["visits"]:
            state["visits"].append(target);state["visits"].sort()
        events.append("source_authored_npc_approached")
    elif action.startswith("ask:"):
        if who is None:raise DialogueActionError("actual speaker is required")
        _spend(state,config["conversation_cost"])
        state["asked_topic"]=action.split(":")[1]
        state["pending"]=None
        _memory(state,config,"original_topic_requested")
        events.append("original_topic_question")
    elif action=="empathize":
        if who is None:raise DialogueActionError("cannot persuade absent speaker")
        _spend(state,config["conversation_cost"])
        if config["choice_consequences"]:
            state["trust"][who]=min(100,state["trust"][who]+config["trust_gain"])
        _memory(state,config,"empathetic_interaction")
        events.append("genuine_social_trust_choice")
    elif action=="offer:aid":
        if who is None or state["favors"]==0:
            raise DialogueActionError("aid needs real recipient and finite stock")
        _spend(state,config["conversation_cost"])
        state["favors"]-=1
        if config["choice_consequences"]:
            state["trust"][who]=min(100,state["trust"][who]+config["gift_trust"])
        _memory(state,config,"finite_resource_aid")
        events.append("resource_backed_original_social_aid")
    elif action=="listen":
        if who is None or state["asked_topic"] is None:
            raise DialogueActionError("witness must first be asked about an actual event")
        if state["dialogue_lines"]>=config["lines_per_scene"]:
            raise DialogueActionError("dialogue line budget exhausted")
        if state["trust"][who]<config["disclosure_threshold"]:
            raise DialogueActionError("source NPC does not trust the player")
        if state["statements"][who]["topic"]!=state["asked_topic"]:
            raise DialogueActionError("resident lacks first-hand topic knowledge")
        _spend(state,config["conversation_cost"])
        state["pending"]=who
        state["dialogue_lines"]+=1
        _memory(state,config,"witness_statement_heard")
        events.append("original_firsthand_statement")
    elif action=="record":
        if who is None or state["pending"]!=who:
            raise DialogueActionError("cannot mint unspoken witness evidence")
        if any(r["speaker"]==who for r in state["records"]):
            raise DialogueActionError("duplicate speaker evidence not independent")
        state["records"].append(dict(state["statements"][who]))
        state["records"].sort(key=lambda r:r["speaker"])
        state["pending"]=None
        events.append("individual_source_custodied_testimony")
    elif action=="challenge":
        if who is None or state["pending"]!=who:
            raise DialogueActionError("cannot challenge non-disclosed testimony")
        if config["choice_consequences"]:
            state["trust"][who]=max(0,state["trust"][who]-config["challenge_cost"])
        state["challenge_count"]+=1
        if not state["statements"][who]["truth"]:
            state["reputation"]+=1
            events.append("fictional_falsehood_exposed")
        else:events.append("false_accusation_degrades_trust")
        state["pending"]=None
        _memory(state,config,"statement_challenged")
    elif action.startswith("verify:"):
        topic=action.split(":")[1]
        if topic in state["verified_topics"]:
            raise DialogueActionError("duplicate event corroboration")
        sources=[r for r in state["records"] if r["topic"]==topic and r["truth"]]
        if len({r["speaker"] for r in sources})<config["min_witnesses"]:
            raise DialogueActionError("independent NPC witness quorum missing")
        if len({r["claim"] for r in sources})!=1:
            raise DialogueActionError("witness claims do not independently agree")
        state["verified_topics"].append(topic);state["verified_topics"].sort()
        state["reputation"]+=2
        events.append("independent_original_world_claim_corrobated")
    elif action=="report":
        if state["checkpoint"] or len(state["verified_topics"])<config["report_target"]:
            raise DialogueActionError("unearned causal quest consequence")
        state["checkpoint"]=True;state["report_count"]+=1
        events.append("nonterminal_witnessed_world_quest_unlocked")
    elif action=="leave":
        state["speaker"]=state["asked_topic"]=state["pending"]=None
        events.append("npc_conversation_closed")
    elif action=="rest":
        state["energy"]=min(config["social_energy"],state["energy"]+config["rest_gain"])
        events.append("social_stamina_recovered")
    elif action=="retire":
        if not state["checkpoint"] or who is not None:
            raise DialogueActionError("ending needs earned objective and ended dialogue")
        state["finished"]=True
        events.append("optional_original_social_story_ending")
    elif action=="inspect":
        events.append("authoritative_npc_world_inspected")
    else:events.append("original_social_world_wait")
    state["turn"]+=1
    _memory(state,config,"time_advanced")
    return events
