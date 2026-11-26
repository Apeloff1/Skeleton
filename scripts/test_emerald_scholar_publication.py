"""Synthetic tamper tests for exact experimental Scholar binary draft transport."""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import publish_emerald_scholar_wingfold as p

class CandidatePublicationTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory()
  self.addCleanup(tmp.cleanup)
  self.root=Path(tmp.name)
  self.data=b"precise-model-bytes"
  self.sha=p.digest(self.data)
  self.manifest={
   'schema':'skeleton.emerald.scholar-wingfold-publication.v1',
   'candidate':'scholar-wingfold-r1','stage':'scholar',
   'bytes':len(self.data),'sha256':self.sha,
   'source_sha256':'a'*64,'donor_sha256':'b'*64,
   'radians':.18,
   'parts':[
     {'path':'assets/emerald/evolution-v5/scholar-wingfold-r1/scholar.glb.part001',
      'offset':0,'bytes':len(self.data),'sha256':self.sha}
   ]
  }
  self.admission={
   'schema':'skeleton.dragon.evolution.experimental-admission.v1',
   'stage':'scholar','candidate':'scholar-wingfold-r1',
   'bytes':len(self.data),'sha256':self.sha,
   'source_sha256':'b'*64,'parent_model_sha256':'a'*64,
   'local_z_radians':.18,'preliminary_clearance_only':True,
   'artist_approved':False,'continuous_collision_qualified':False,
   'equipment_enabled':False,'release_qualified':False,
  }

 def bundle(self,model=None,extra=None,admission=None):
  path=self.root/'payload.zip'
  with zipfile.ZipFile(path,'w') as archive:
   archive.writestr('scholar.glb',self.data if model is None else model)
   archive.writestr('admission.json',json.dumps(
    self.admission if admission is None else admission))
   if extra:archive.writestr(extra,b'hostile')
  return path

 def test_real_pinned_manifest_complete(self):
  m,_=p.load()
  self.assertEqual(m['bytes'],113305100)
  self.assertEqual(m['sha256'],
   '3bf57f602c905c1c6864c2fdddcc7df3bd79699bcbccab0c5c2d83480fa7b877')
  self.assertEqual(len(m['parts']),4)
  self.assertEqual(sum(x['bytes'] for x in m['parts']),m['bytes'])
  self.assertEqual(m['donor_sha256'],
    'c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a')

 def test_exact_original_slice_bundle(self):
  self.assertEqual(list(p.chunks(self.bundle(),self.manifest)),
                   [(self.manifest['parts'][0],self.data)])

 def test_same_length_corruption_rejected(self):
  bad=b'X'+self.data[1:]
  with self.assertRaisesRegex(ValueError,'digest|chunk'):
   list(p.chunks(self.bundle(model=bad),self.manifest))

 def test_different_length_rejected(self):
  with self.assertRaisesRegex(ValueError,'model size'):
   list(p.chunks(self.bundle(model=self.data[:-1]),self.manifest))

 def test_wrong_parent_digest_rejected(self):
  a=dict(self.admission,parent_model_sha256='0'*64)
  with self.assertRaisesRegex(ValueError,'admission'):
   list(p.chunks(self.bundle(admission=a),self.manifest))

 def test_forged_artist_approval_rejected(self):
  a=dict(self.admission,artist_approved=True)
  with self.assertRaisesRegex(ValueError,'admission'):
   list(p.chunks(self.bundle(admission=a),self.manifest))

 def test_false_collision_claim_rejected(self):
  a=dict(self.admission,continuous_collision_qualified=True)
  with self.assertRaisesRegex(ValueError,'admission'):
   list(p.chunks(self.bundle(admission=a),self.manifest))

 def test_hostile_path_rejected(self):
  with self.assertRaisesRegex(ValueError,'unsafe ZIP'):
   list(p.chunks(self.bundle(extra='../escape'),self.manifest))

 def test_reject_unauthorized_remote(self):
  with patch.object(p,'git',side_effect=[b'https://github.com/Apeloff1/Skeleton.git\n',
                                        b'https://hostile.invalid/other.git\n']):
   with self.assertRaisesRegex(ValueError,'remote not authorized'):
    p.check_remote(self.root)

 def test_missing_remote_tree_must_fail(self):
  with self.assertRaisesRegex(ValueError,'required binary'):
   p.verify_tree(self.root,self.manifest)

 def test_exact_reconstructed_tree(self):
  chunk=self.manifest['parts'][0]
  path=self.root/chunk['path']
  path.parent.mkdir(parents=True)
  path.write_bytes(self.data)
  evidence=p.verify_tree(self.root,self.manifest)
  self.assertTrue(evidence['binary_integrity_qualified'])
  self.assertFalse(evidence['collision_qualified'])
  self.assertFalse(evidence['release_qualified'])

 def test_tree_tamper_fails(self):
  chunk=self.manifest['parts'][0]
  path=self.root/chunk['path']
  path.parent.mkdir(parents=True)
  path.write_bytes(b'X'+self.data[1:])
  with self.assertRaisesRegex(ValueError,'chunk digest'):
   p.verify_tree(self.root,self.manifest)

if __name__=='__main__':
 unittest.main(verbosity=2)
