"""Original NPC market, professions, authored craft input and social rumor lanes.

No imaginary assets or LLM speech. Resources are conserved through explicit
debits/credits; witnessed stories retain their provenance and secondhand
rumors decrease certainty. Economic and epistemic state can be replayed.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .contracts import canonical_digest
from .npc_society_runtime import (
    Society, SocietyError, Memory, Mind, Citizen, _remember,
)

GOODS=("grain","herb","wood","ore","cloth","ink","tools","food")
COST={"grain":4,"herb":7,"wood":5,"ore":9,"cloth":8,
      "ink":6,"tools":13,"food":5}
PRODUCTION={
    "grower":("grain",None,2),
    "healer":("herb",None,1),
    "artisan":("cloth","grain",1),
    "builder":("tools","wood",1),
    "cook":("food","grain",1),
    "scribe":("ink","herb",1),
    "watcher":("wood",None,1),
    "explorer":("ore",None,1),
    "courier":("food",None,1),
    "mediator":("cloth",None,1),
    "scholar":("ink",None,1),
    "guard":("tools","ore",1),
}


class EconomyError(ValueError):
    """Game market or rumor operation lacks adequate real-world state."""


@dataclass(frozen=True, slots=True)
class Account:
    owner: str
    coins: int
    goods: tuple[tuple[str,int],...]

    def __post_init__(self):
        if type(self.coins) is not int or not 0 <= self.coins <= 100000:
            raise EconomyError("bounded original-world currency required")
        if any(g not in GOODS or type(q) is not int or not 0 <= q <= 255
               for g,q in self.goods):
            raise EconomyError("invalid original trade stock")
        if len({g for g,q in self.goods})!=len(self.goods):
            raise EconomyError("duplicated resource denominations")

    def payload(self):
        return dict(owner=self.owner,coins=self.coins,
                    goods=[list(x) for x in self.goods])


@dataclass(frozen=True, slots=True)
class MarketEvent:
    turn: int
    kind: str
    from_actor: str
    to_actor: str
    resource: str
    amount: int
    coins: int

    def payload(self):
        return dict(turn=self.turn,kind=self.kind,from_actor=self.from_actor,
                    to_actor=self.to_actor,resource=self.resource,
                    amount=self.amount,coins=self.coins)


@dataclass(frozen=True, slots=True)
class Economy:
    society_digest: str
    accounts: tuple[Account,...]
    events: tuple[MarketEvent,...] = ()
    turn: int = 0

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.npc_original_economy.v1",
                    society_digest=self.society_digest,
                    accounts=[a.payload() for a in self.accounts],
                    events=[e.payload() for e in self.events],turn=self.turn)


def new_economy(society: Society, *, authorized: bool) -> Economy:
    if not authorized:
        raise PermissionError("original market creation requires authority")
    if not isinstance(society,Society):
        raise EconomyError("typed original NPC society required")
    accounts=[]
    for i,profile in enumerate(society.profiles):
        items={"grain":2+i%2,"wood":1+i%3,"herb":1,"ore":1,
               "cloth":0,"ink":0,"tools":0,"food":2}
        accounts.append(Account(profile.key,100+i%50,tuple(sorted(items.items()))))
    return Economy(society.world_digest,tuple(accounts))


def price(economy: Economy,resource: str,*,region_keys: tuple[str,...]) -> int:
    if resource not in COST:
        raise EconomyError("unsupported resource type")
    region=set(region_keys)
    stock=sum(dict(a.goods).get(resource,0) for a in economy.accounts
              if a.owner in region)
    # Local scarcity multiplier capped to prevent resource price overflow.
    return min(50,max(1,COST[resource]+30//(1+stock)))


def produce_goods(economy: Economy,society: Society,*,authorized: bool) -> Economy:
    if not authorized:
        raise PermissionError("world profession shift needs authority")
    if economy.society_digest!=society.world_digest:
        raise EconomyError("resources belong to another original world")
    if type(economy.turn) is not int or society.turn<=economy.turn:
        raise EconomyError("profession production requires a new authoritative world turn")
    if len(economy.accounts)!=len(society.profiles):
        raise EconomyError("missing exact per-NPC resource account")
    results=[]
    events=list(economy.events)
    for p,m,a in zip(society.profiles,society.minds,economy.accounts):
        if p.key!=a.owner or p.key!=m.key:
            raise EconomyError("resource production has mismatched citizen identity")
        goods=dict(a.goods)
        output,consumes,count=PRODUCTION.get(p.profession,("food","grain",1))
        if (m.intent=="work" and m.scene==p.workplace
                and (consumes is None or goods.get(consumes,0)>=1)
                and goods.get(output,0)+count<=255):
            # Validate the output slot before committing any input debit.
            # A full workshop cannot silently destroy raw materials.
            if consumes:
                goods[consumes]-=1
            goods[output]=goods.get(output,0)+count
            events.append(MarketEvent(society.turn,"produce",p.key,p.key,
                                      output,count,0))
        results.append(replace(a,goods=tuple(sorted(goods.items()))))
    if len(events)>4096:
        raise EconomyError("economy history requires controlled archival")
    return Economy(economy.society_digest,tuple(results),tuple(events),society.turn)


def transact(economy: Economy,society: Society,*,seller: str,
             buyer: str,resource: str,quantity: int,
             authorized: bool) -> Economy:
    if not authorized:
        raise PermissionError("NPC exchange requires local operator authority")
    if seller==buyer or type(quantity) is not int or not 1<=quantity<=16:
        raise EconomyError("buyer/seller or bounded quantity invalid")
    if economy.society_digest!=society.world_digest:
        raise EconomyError("foreign economy")
    owners={a.owner:a for a in economy.accounts}
    minds={m.key:m for m in society.minds}
    if seller not in owners or buyer not in owners:
        raise EconomyError("invented market participant")
    if minds[seller].scene!=minds[buyer].scene:
        raise EconomyError("market actors must actually meet in one original scene")
    region_keys=tuple(m.key for m in society.minds
                      if m.scene==minds[seller].scene)
    rate=price(economy,resource,region_keys=region_keys)
    amount=rate*quantity
    from_a,to_a=owners[seller],owners[buyer]
    seller_stock=dict(from_a.goods)
    buyer_stock=dict(to_a.goods)
    if seller_stock.get(resource,0)<quantity or to_a.coins<amount:
        raise EconomyError("trade cannot generate unowned resources or negative currency")
    if buyer_stock.get(resource,0)+quantity>255 or from_a.coins+amount>100000:
        raise EconomyError("trade exceeds inventory or coin cap")
    seller_stock[resource]-=quantity
    buyer_stock[resource]=buyer_stock.get(resource,0)+quantity
    owners[seller]=replace(from_a,coins=from_a.coins+amount,
                           goods=tuple(sorted(seller_stock.items())))
    owners[buyer]=replace(to_a,coins=to_a.coins-amount,
                          goods=tuple(sorted(buyer_stock.items())))
    if len(economy.events)>=4096:
        raise EconomyError("trade receipts need controlled archival")
    event=MarketEvent(society.turn,"trade",seller,buyer,resource,quantity,amount)
    return replace(economy,accounts=tuple(owners[a.owner] for a in economy.accounts),
                   events=(*economy.events,event))


def diffuse_witnessed_memory(society: Society,*,subject: str,
                             max_recipients: int=32,authorized: bool) -> Society:
    """Physical colocated rumor diffusion; no omniscient telepathy.

    Only directly observed memories are source evidence. Derived reports
    have reduced certainty and retain origin as 'rumor'.
    """
    if not authorized:
        raise PermissionError("epistemic rumor diffusion requires authorization")
    if type(max_recipients) is not int or not 0<=max_recipients<=512:
        raise EconomyError("bounded observed report transmission required")
    sources={}
    for mind in society.minds:
        for memory in mind.memories:
            if memory.subject==subject and memory.origin=="observed":
                key=(mind.scene,memory.event,memory.subject)
                old=sources.get(key)
                if old is None or memory.certainty>old.certainty:
                    sources[key]=memory
    remaining=max_recipients
    updated=[]
    for mind in society.minds:
        member=mind
        seen={(m.event,m.subject) for m in member.memories}
        for (scene,event,who),original in sorted(sources.items()):
            if remaining<=0:
                break
            if scene!=member.scene or (event,who) in seen:
                continue
            certainty=max(0,original.certainty-25)
            if certainty<40:
                continue
            echoed=Memory(event,who,scene,society.turn,
                          original.valence*3//4,certainty,"rumor")
            member=_remember(member,echoed)
            remaining-=1
            seen.add((event,who))
        updated.append(member)
    return replace(society,minds=tuple(updated),latest_event="rumor_diffusion")


def citizen_dialogue(society: Society,citizen_key: str,*,player_subject: str="hero") -> dict:
    profiles={p.key:p for p in society.profiles}
    states={m.key:m for m in society.minds}
    if citizen_key not in profiles:
        raise EconomyError("unknown original citizen")
    p,m=profiles[citizen_key],states[citizen_key]
    known=[x for x in m.memories if x.subject==player_subject]
    trusted=max(known,key=lambda x:(x.certainty,abs(x.valence),x.turn),
                default=None)
    attitude="cautious" if not known else (
        "welcoming" if sum(x.valence*x.certainty for x in known)>0 else
        "concerned"
    )
    detail=("I have not personally witnessed your deeds." if not trusted else
            ("I saw " if trusted.origin=="observed" else "I heard about ")+
            trusted.event.replace("_"," ")+".")
    line=(f"{p.name}, the {p.profession}, is {attitude}. "
          f"My priority is {p.motive}; I feel {m.intent}. {detail}")
    return dict(schema="skeleton.game_builder.original_npc_dialogue.v1",
                citizen=p.key,scene=m.scene,
                line=line,attitude=attitude,
                source_memory=trusted.payload() if trusted else None,
                language_model_generated=False,
                canon_verified=False)


__all__=[
    "EconomyError","Account","MarketEvent","Economy","new_economy",
    "price","produce_goods","transact","diffuse_witnessed_memory",
    "citizen_dialogue",
]
