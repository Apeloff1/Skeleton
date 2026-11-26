"""Synthetic canonical Python treasury wire projections for frontend contract tests.

No network, real user data, database or model access. All times, URLs and
retained text are fixture constants; only actual build_treasury output is used.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from skeleton.ai.webcrawler.dragon_treasury import Observation, build_treasury

NOW=1_800_000_000.
BASE="https://example.org"


def observation(i:int,url:str,text:str,stamp:float,*,history:bool=False)->Observation:
    session=f"expedition-{i//60}"
    source=hashlib.sha256(f"{i}:{url}:{stamp}".encode()).hexdigest()
    raw=hashlib.sha256(text.encode()).hexdigest()
    return Observation(session,source,url,raw,stamp,text,NOW+86400,
                       "text/plain","public",None,True,True,history)


def fixture()->dict:
    target=BASE+"/instrument"
    rows=[observation(0,target,"Historical calibration: relic magnetometer 10 degrees.",
                      NOW-3*86400,history=True),
          observation(1,target,"Current calibration: magnetometer telescope 20 degrees.",
                      NOW-2*86400)]
    rows.extend(observation(i,BASE+f"/article/{i}",
                            "Optical measurements and telescope catalogue "+str(i),NOW-i)
                for i in range(2,300))

    def project(mode,query,source_rows,**kwargs):
        value=build_treasury(source_rows,as_of=NOW,growth=600,mode=mode,query=query,**kwargs)
        return {"ok":True,**value,"invalid_materialized_segments":0,"legacy_history_sessions":0}

    vault_rows=[replace(row,archive_only=True,refresh_allowed=False) for row in rows[:2]]
    selected=tuple(sorted({row.session_id for row in vault_rows}))
    vault=build_treasury(vault_rows,as_of=NOW,growth=0,mode="historic_only",query="magnetometer",
                         catalogue_scope=selected,candidate_limit_reached=True)
    vault={"ok":True,**vault,"vault_window":list(selected),"invalid_materialized_segments":0,
           "legacy_history_sessions":0}
    return {
        "vault":vault,
        "normal":project("current_only","magnetometer",rows[:2]),
        "capped":project("current_only","magnetometer",rows),
        "historic":project("historic_only","relic",rows),
        "at_time":project("at_time","relic",rows,observed_before=NOW-2.5*86400),
    }


if __name__=="__main__":
    print(json.dumps(fixture(),allow_nan=False,sort_keys=True))
