"""Run original-source-bound V7 crossfades on two exact exported V7 GLBs.

Imports the reviewed V6 geometry/crossfade engine but supplies immutable V7
model pins. No continuous CCD, Three.js runtime, GPU or release approval.
"""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
import emerald_v6_crossfade_screen as engine
from emerald_v7_orbit02 import OUTPUTS, DONOR, require

SCHEMA='skeleton.emerald.v7.orbit02-crossfade-mesh-screen.v1'

def run(stage,model,tools,steps=3,time_budget=600,checkpoint=None,resume=False):
 require(stage in OUTPUTS and
         type(steps) is int and 3<=steps<=17 and
         60<=time_budget<=3600, 'outside reviewed source/model and sampling budget')
 source=Path(model)
 expected_bytes,sha=OUTPUTS[stage]
 require(source.is_file() and not source.is_symlink() and
         source.stat().st_size==expected_bytes and engine.sha(source)==sha,
         'V7 exact original model custody failed')
 report=engine.run(stage,source,tools,steps,limit_seconds=time_budget,
                   journal=checkpoint,resume=resume,pins=OUTPUTS)
 require(report['model_sha256']==sha and report['model_bytes']==expected_bytes
         and report['donor_sha256']==DONOR, 'unexpected V7 model report identity')
 report['schema']=SCHEMA
 report['generation']='v7'
 report['source_v6_sha256']={
   'pathfinder':'20d6a6a62b3ff232572e1b25d799f1461d4e343ce3b7d30a328faed8837c4063',
   'archivist':'8d72d43773a98444133ab628db552bddad06ea0f101cfe223897bf8ba0944973',
 }[stage]
 report['orbital_source_tail_root_corrected']=True
 report['sampled_screen_complete']=len(report['samples'])==len(engine.TRANSITIONS)*steps
 report['full_continuous_interval_qualification']=False
 report['live_three_mixer_qualification']=False
 report['artistic_approval']=False
 report['physical_rtx_approval']=False
 report['release_qualified']=False
 return report

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--stage',required=True,choices=OUTPUTS)
 p.add_argument('--model',required=True,type=Path)
 p.add_argument('--source-tools',required=True,type=Path)
 p.add_argument('--output',required=True,type=Path)
 p.add_argument('--steps',type=int,default=3)
 p.add_argument('--time-budget-seconds',type=float,default=600)
 p.add_argument('--checkpoint',type=Path)
 p.add_argument('--resume',action='store_true')
 a=p.parse_args()
 require(a.output.parent.is_dir() and not a.output.parent.is_symlink() and
         not os.path.lexists(a.output), 'trusted unused report path required')
 result=run(a.stage,a.model,a.source_tools,a.steps,a.time_budget_seconds,
            checkpoint=a.checkpoint,resume=a.resume)
 with a.output.open('x',encoding='utf-8') as out:
  json.dump(result,out,indent=2,allow_nan=False);out.write('\n')
 print(json.dumps({k:v for k,v in result.items() if k!='samples'},indent=2))
 if result['observed_new_contact_instances']>0:
  raise SystemExit(2)

if __name__=='__main__':main()
