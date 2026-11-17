"""Strict consistency gate for sampled contact receipts, never physical proof."""
import argparse
import json
import math
from pathlib import Path
from emerald_v4_contact_scan import PAIRS

SCHEMA='skeleton.emerald.sampled-triangle-contact.v2'

def verify(report,pin):
 if not isinstance(report,dict) or report.get('schema')!=SCHEMA or report.get('scan_complete') is not True:
  raise ValueError('incomplete or wrong scanner receipt')
 stage=report.get('stage')
 model=pin['forms'].get(stage)
 if (not model or report.get('donor_sha256')!=pin['donorSha256']
     or report.get('sha256')!=model['sha256'] or report.get('bytes')!=model['bytes']
     or model['equipmentEnabled'] is not False):
  raise ValueError('stale or conflicting source/gear pin')
 for key in ('continuous_collision_qualified','all_morphs_qualified','optional_equipment_enabled',
             'physical_rtx_verified','artist_approved','release_qualified'):
  if report.get(key) is not False:
   raise ValueError('unjustified qualification claim: '+key)
 clips=report.get('clips')
 fractions=report.get('fractions')
 if (not isinstance(clips,list) or not clips or len(clips)>380 or
     len(set(clips))!=len(clips) or
     any(not isinstance(x,str) or not x or x.startswith('growth-') for x in clips)):
  raise ValueError('unsupported clip selection')
 if (not isinstance(fractions,list) or not (2<=len(fractions)<=257)
     or fractions[0]!=0 or fractions[-1]!=1
     or any(not isinstance(x,(float,int)) or not math.isfinite(x)
            or not 0<=x<=1 for x in fractions)
     or any(b<=a for a,b in zip(fractions,fractions[1:]))):
  raise ValueError('temporal sample policy invalid')
 poses=report.get('poses')
 if (poses!=len(clips)*len(fractions) or
     report.get('unresolved_nonlinear_intervals')!=len(clips)*(len(fractions)-1)):
  raise ValueError('silent omission of poses or intervals')
 census=report.get('triangle_coverage')
 if (not isinstance(census,dict) or census.get('classified_triangles',0)<=0
     or census.get('unclassified_seam_and_other_triangles',0)<=0
     or census['classified_triangles']+census['unclassified_seam_and_other_triangles']!=719312):
  raise ValueError('untrustworthy anatomical scope')
 evidence=report.get('evidence')
 if not isinstance(evidence,list) or len(evidence)!=poses:
  raise ValueError('missing pose evidence')
 total=0
 names=[a+'__'+b for a,b in PAIRS]
 for i,row in enumerate(evidence):
  if row.get('clip')!=clips[i//len(fractions)] or row.get('fraction')!=fractions[i%len(fractions)]:
   raise ValueError('incorrect pose ordering')
  contacts=row.get('contacts')
  if not isinstance(contacts,dict) or list(contacts)!=names:
   raise ValueError('incomplete high-risk pair census')
  for item in contacts.values():
   fields=('candidate_pairs','contact_count','near_count','root_centerline_contacts','distal_contacts')
   if any(not isinstance(item.get(k),int) or item[k]<0 for k in fields):
    raise ValueError('invalid triangle count')
   if (item['contact_count']!=item['root_centerline_contacts']+item['distal_contacts']
       or item['contact_count']+item['near_count']>item['candidate_pairs']):
    raise ValueError('inconsistent contact count')
   total+=item['contact_count']
 if total!=report.get('sampled_contact_count'):
  raise ValueError('aggregate collision count mismatch')
 return {
  'schema':'skeleton.emerald.contact-evidence-consistency.v1',
  'stage':stage,'source_sha256':model['sha256'],
  'poses_consistent':poses,'classified_triangles':census['classified_triangles'],
  'unresolved_nonlinear_intervals':report['unresolved_nonlinear_intervals'],
  'sampled_contacts':total,'sampled_zero_contact':total==0,
  'continuous_collision_qualified':False,'equipment_enabled':False,
  'artist_approved':False,'release_qualified':False,
 }

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--receipt',type=Path,required=True)
 p.add_argument('--pin',type=Path,
     default=Path(__file__).resolve().parents[1]/
         'frontend/src/features/Jeeves/companion/atelier/evolutionPin.json')
 p.add_argument('--require-zero',action='store_true')
 args=p.parse_args()
 result=verify(json.loads(args.receipt.read_bytes()),json.loads(args.pin.read_bytes()))
 print(json.dumps(result,indent=2))
 if args.require_zero and result['sampled_contacts']:
  raise SystemExit(2)

if __name__=='__main__':main()
