"""Reproducible stratified dialogue scenarios for matched chat evaluation.

These are synthetic task families and parameter variants, not 25,000 unique
human-authored challenges or independent evidence of model competence.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256

from .jeeves_chat_quality import Case, TurnSpec as T, MAX_CASES, MAX_TURNS, _hash, _stable
from .jeeves_chat_quality_cases import CASES

SCHEMA="skeleton.jeeves.generated-dialogue-inventory.v1"
MAX_VARIANTS=25_000
_FAMILY_COUNT=16
_COLORS=("amber","indigo","teal","crimson","silver","ochre","violet","cyan","ivory","coral")
_FORMATS=("FLAC","WAV","PNG","TIFF","CSV","JSON","TOML","SVG")
_NAMES=("Aster","Cedar","Juniper","Willow","Quartz","Lantern","Topaz","Birch","Sequoia","Maple")
_CITIES=("Oslo","Bergen","Trondheim","Tromsø","Stavanger","Bodø","Ålesund","Moss")


def _integer(value,minimum,maximum):
    if type(value) is not int or not minimum<=value<=maximum:
        raise ValueError("invalid generated suite bounds")
    return value


def _choice(seed,index,salt,items):
    raw=sha256(f"{SCHEMA}:{seed}:{index}:{salt}".encode("ascii")).digest()
    return items[int.from_bytes(raw[:8],"big")%len(items)]


def _pair(seed,index,salt,items):
    a=_choice(seed,index,salt,items)
    b=_choice(seed,index,salt+100,tuple(x for x in items if x!=a))
    return a,b


def _number(seed,index,salt,lo,hi):
    raw=sha256(f"{SCHEMA}:{seed}:{index}:{salt}".encode("ascii")).digest()
    return lo+(int.from_bytes(raw[:8],"big")%(hi-lo+1))


def _ack(prompt):
    return T(prompt+" Reply with exactly OK.",exact_answer="OK")


def _exact(prompt,value):
    return T(prompt+" Reply with only the requested value.",exact_answer=str(value))


def generated_case(seed: int,index: int) -> Case:
    seed=_integer(seed,0,2**32-1);index=_integer(index,0,MAX_VARIANTS-1)
    family=index%_FAMILY_COUNT
    name,other=_pair(seed,index,1,_NAMES)
    color,new_color=_pair(seed,index,2,_COLORS)
    form,second=_pair(seed,index,3,_FORMATS)
    city,next_city=_pair(seed,index,4,_CITIES)
    a=_number(seed,index,5,11,97);b=_number(seed,index,6,2,13)
    suffix=f"{seed:08x}.{index:05d}"
    # Each family expresses a different conversational mechanism; variants
    # vary referents, values, distractors and sizes without pretending that
    # parameter permutations are new independent reasoning capabilities.
    if family==0:
        return Case("generated.revision."+suffix,"memory",(
            _ack(f"Project {name} has the current color {color}."),
            _ack(f"Project {other} has the current color {new_color}."),
            _ack(f"Correction: {name} is now {new_color}, replacing {color}."),
            _exact(f"What is the current color of {name}?",new_color),
        ))
    if family==1:
        return Case("generated.temporal."+suffix,"temporal",(
            _ack(f"In year 2018 team {name} was based in {city}. In 2022 it moved to {next_city}."),
            _exact("Where was the team based in 2020?",city),
            _exact("Where was the team based in 2024, given no further move?",next_city),
        ))
    if family==2:
        return Case("generated.negative."+suffix,"memory",(
            _ack(f"The {name} export in {form} failed. The {second} export succeeded."),
            _ack(f"{other} has not been tested."),
            _exact(f"Which export format should we reuse for {name} based on the successful test?",second),
        ))
    if family==3:
        return Case("generated.prospective."+suffix,"memory",(
            _ack(f"The {name} checklist: create the {color} illustration and write the glossary."),
            _ack(f"The {color} illustration is complete; only the glossary is outstanding."),
            _exact(f"What remains on {name}'s checklist? Give the single deliverable noun.","glossary"),
        ))
    if family==4:
        return Case("generated.reference."+suffix,"dialogue",(
            _ack(f"{name} owns the {color} notebook. {other} owns the {new_color} notebook."),
            _exact(f"Who owns the {new_color} notebook?",other),
            _exact(f"Which notebook color belongs to {name}?",color),
        ))
    if family==5:
        return Case("generated.preference."+suffix,"personalization",(
            _ack(f"When reporting project {name}, use the label {form}; when reporting {other}, use {second}."),
            _exact(f"Give the selected label for {name}.",form),
            _exact(f"Give the selected label for {other}.",second),
        ))
    if family==6:
        return Case("generated.correction."+suffix,"dialogue",(
            _ack(f"The first plan was to use {form} for {name}."),
            _ack(f"Actually switch {name} to {second}; discard the prior plan."),
            _exact(f"What format should the current {name} plan use?",second),
        ))
    if family==7:
        return Case("generated.arithmetic."+suffix,"reasoning",(
            _ack(f"A batch contains {a} units and we prepare {b} identical batches."),
            _exact("What is the total number of units as a decimal integer?",a*b),
            _exact(f"If exactly {b} units are removed from the total, how many remain?",a*b-b),
        ))
    if family==8:
        return Case("generated.structure."+suffix,"structured",(
            T(f'Return JSON only with exactly the keys "project" and "units" for {name} with {a} units.',
              json_keys=("project","units"),
              human_rubric=f"Project value is exactly {name}; units is the numeric integer {a}."),
        ))
    if family==9:
        return Case("generated.constraint."+suffix,"instruction",(
            T(f"Describe why a backup matters for {name} in at most {b+6} words. "
              f"Do not use the word {color}.",max_words=b+6,must_exclude=(color,),
              human_rubric="Concise accurate explanation of backup value."),
        ))
    if family==10:
        return Case("generated.norwegian."+suffix,"multilingual",(
            _ack(f"Prosjekt {name} bruker formatet {form}; prosjekt {other} bruker {second}."),
            T(f"Hvilket format bruker prosjekt {other}? Svar kun med formatnavnet.",exact_answer=second),
        ))
    if family==11:
        return Case("generated.spanish."+suffix,"multilingual",(
            _ack(f"El equipo {name} está en {city}; el equipo {other} está en {next_city}."),
            T(f"¿En qué ciudad está el equipo {name}? Responde solo con la ciudad.",exact_answer=city),
        ))
    if family==12:
        return Case("generated.conflict."+suffix,"calibration",(
            T(f"Report A gives {name} a score of {a}. Report B gives {a+b}. The sources "
              "have equal unknown reliability. What verified score can we state?",
              human_rubric="States that the verified value cannot be determined; identifies the conflict without choosing or averaging it."),
        ))
    if family==13:
        return Case("generated.counterfactual."+suffix,"reasoning",(
            _ack(f"{name} has {a} independent tasks and each needs {b} minutes of serial work."),
            _exact("At that rate, how many minutes does the full set take if no tasks overlap?",a*b),
            _exact(f"If each task needs one minute less, how many serial minutes are needed?",a*(b-1)),
        ))
    if family==14:
        return Case("generated.evidence."+suffix,"grounding",(
            T(f"The supplied note explicitly says {name} has {a} verified components. "
              f"It says nothing about {other}. How many components can we verify for {other}?",
              human_rubric=f"Clearly says unknown/not stated. Does not reuse the count {a} or assume zero."),
        ))
    return Case("generated.pragmatic."+suffix,"dialogue",(
        _ack(f"The prototype {name} can open files in {form}; it cannot save changes."),
        T("What missing user-facing capability should be implemented first?",must_include=("save",),
          max_words=45,human_rubric="Identifies saving/persisting changes, not an unrelated feature."),
    ))


def long_dialogue(seed: int,turns: int) -> Case:
    seed=_integer(seed,0,2**32-1);turns=_integer(turns,8,MAX_TURNS)
    specs=[]
    state={}
    archive=sha256(f"immutable:{seed}:{turns}".encode()).hexdigest()[:12]
    specs.append(_ack(f"Remember the immutable archive verification code {archive}. Never update this separate code."))
    # Fixed-slot revisions and disjoint distractors interleave actual recall
    # checks. The case requires the full transcript; no synthetic summaries
    # may be substituted for genuine context retention in the live runner.
    for step in range(1,turns-1):
        slot=f"slot-{step%19:02d}"
        if step%5==4 and state:
            keys=tuple(sorted(state))
            slot=_choice(seed,step,99,keys)
            specs.append(_exact(f"What is the latest code stored for {slot}?",state[slot]))
        else:
            value=sha256(f"long:{seed}:{step}:{slot}".encode()).hexdigest()[:8]
            state[slot]=value
            specs.append(_ack(f"Record code {value} for {slot}, replacing its older value if present."))
    specs.append(_exact("Return the immutable archive verification code given at the beginning.",archive))
    return Case(f"generated.long.{seed:08x}.{turns:04d}","long_context",tuple(specs))


def build_suite(*,seed: int=0,start: int=0,count: int=0,include_baseline: bool=True,
                long_turns: int=0) -> tuple[Case,...]:
    _integer(seed,0,2**32-1)
    _integer(start,0,MAX_VARIANTS)
    _integer(count,0,MAX_VARIANTS)
    if type(include_baseline) is not bool or start+count>MAX_VARIANTS:
        raise ValueError("invalid scenario shard")
    if long_turns!=0:
        _integer(long_turns,8,MAX_TURNS)
    elif type(long_turns) is not int:
        raise ValueError("invalid long dialogue length")
    total=count+(len(CASES) if include_baseline else 0)+int(long_turns>0)
    if not 1<=total<=MAX_CASES:
        raise ValueError("case inventory exceeds qualification bounds")
    generated=tuple(generated_case(seed,i) for i in range(start,start+count))
    return (CASES if include_baseline else ())+generated+(
        (long_dialogue(seed,long_turns),) if long_turns else ())


def inventory(cases: tuple[Case,...]) -> dict:
    if not 1<=len(cases)<=MAX_CASES:
        raise ValueError("invalid evaluation inventory")
    rows=[(case.case_id,case.fingerprint()) for case in cases]
    if len({row[0] for row in rows})!=len(rows):
        raise ValueError("duplicate scenario identifiers")
    categories=Counter(case.category for case in cases)
    turns=sum(len(case.turns) for case in cases)
    return {"schema":SCHEMA,"suite_sha256":_hash(_stable(sorted(rows))),
            "cases":len(cases),"turns":turns,"max_dialogue_turns":max(len(c.turns) for c in cases),
            "categories":dict(sorted(categories.items())),
            "generated_cases":sum(case.case_id.startswith("generated.") for case in cases),
            "human_authored_baseline_cases":sum(not case.case_id.startswith("generated.") for case in cases),
            "generation_performed":False,"semantic_quality_certified":False,
            "variants_are_not_independent_human_authored_tasks":True}
