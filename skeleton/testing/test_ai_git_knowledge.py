"""Exact-Git-object AI code knowledge admission with fail-closed custody."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json,os,subprocess,tempfile,sqlite3,unittest
from unittest.mock import patch
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.context.knowledge_plane import KnowledgePlane,KnowledgeError,KnowledgePolicy
from skeleton.ai.runtime.operational_ai.context.knowledge_plane.repository import (
    GitSource,GitIndexItem,GitSourceError,index_repository)
from skeleton.ai.runtime.operational_ai.context.knowledge_plane.repository.contracts import (
    git_path,document_for_path)
from skeleton.ai.runtime.operational_ai.context.knowledge_plane.repository.doctor import inspect_repository
from skeleton.ai.runtime.operational_ai.context.knowledge_plane.repository.sensitivity import require_publicly_indexable
from skeleton.ai.runtime.operational_ai.context.knowledge_plane.repository.cli import main as cli
from skeleton.ai.runtime.operational_ai.deployment.boot.identity import PrincipalBinding,establish_binding

M='c'*64;T='d'*64

class GitKnowledge(unittest.TestCase):
    def git(self,*args):
        r=subprocess.run(['git','-C',str(self.repo),*args],stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,timeout=10,check=True)
        return r.stdout.decode().strip()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='git-kb-', dir=Path.home())
        self.root=Path(self.temp.name)
        self.repo=self.root/'repository';self.repo.mkdir(mode=0o700)
        self.git('init','-q');self.git('config','user.email','fixture@example.invalid')
        self.git('config','user.name','Test Fixture')
        self.code=self.repo/'skeleton'/'ai'/'runtime';self.code.mkdir(parents=True)
        (self.code/'source.py').write_text('"""Real source."""\nLANGUAGE = "Python"\nGUIDANCE = "Use a deterministic runtime."\n',encoding='utf8')
        (self.code/'other.py').write_text('SUPPORTED = True\n',encoding='utf8')
        self.git('add','.');self.git('commit','-qm','first source')
        self.head=self.git('rev-parse','HEAD')
        self.state=self.root/'state';self.state.mkdir(mode=0o700)
        self.identity=Identity('tenant','reader',M,T)
        establish_binding(self.state,PrincipalBinding('tenant','reader',M,T))
        self.db=SpineDatabase(self.state)
        self.plane=KnowledgePlane(self.db,self.identity,policy=KnowledgePolicy(
            max_document_bytes=32768,max_total_bytes=200000,max_documents=20,
            max_chunks=100,chunk_characters=256,chunk_overlap=32,
            max_scan_rows=1000))

    def tearDown(self):
        self.db.close();self.temp.cleanup()

    def item(self,name='source.py',revision=0):
        return GitIndexItem('skeleton/ai/runtime/'+name,revision,'operator-authored')

    def index(self,items=None,head=None):
        return index_repository(self.plane,repo_root=self.repo,commit=head or self.head,
                    items=items if items is not None else (self.item(),),approved=True)

    def test_commit_verified_and_source_retrievable(self):
        outcome=self.index()
        self.assertEqual(len(outcome),1)
        self.assertEqual(outcome[0]['commit_sha'],self.head)
        self.assertTrue(self.plane.search('deterministic runtime'))
        attested=inspect_repository(self.plane,repo_root=self.repo)
        self.assertEqual(attested['verified'],1)
        self.assertEqual(attested['remote_fetches'],0)

    def test_exact_commit_ignores_dirty_worktree(self):
        (self.code/'source.py').write_text('SENSITIVE_WRONG_UNCOMMITTED_CONTENT=3')
        self.index()
        hits=self.plane.search('deterministic')
        self.assertTrue(hits)
        self.assertFalse(self.plane.search('SENSITIVE_WRONG_UNCOMMITTED_CONTENT'))

    def test_changed_commit_requires_new_exact_source_revision(self):
        self.index()
        (self.code/'source.py').write_text('"""Version two."""\nMATERIAL = "planet Jupiter"\n')
        self.git('add','.');self.git('commit','-qm','second')
        next_head=self.git('rev-parse','HEAD')
        value=self.index((self.item(revision=1),),head=next_head)
        self.assertEqual(value[0]['revision'],2)
        self.assertTrue(self.plane.search('Jupiter'))
        self.assertFalse(self.plane.search('deterministic'))
        self.assertEqual(inspect_repository(self.plane,repo_root=self.repo)['verified'],2)

    def test_wrong_parent_revision_does_not_change_provenance(self):
        self.index()
        (self.code/'source.py').write_text('New material to be rejected')
        self.git('add','.');self.git('commit','-qm','version2')
        with self.assertRaises(KnowledgeError):self.index(head=self.git('rev-parse','HEAD'))
        self.assertEqual(self.plane.list()[0]['revision'],1)

    def test_git_path_traversal_and_credentials_names_fail_closed(self):
        for path in ('../etc/passwd','skeleton/ai/.env','skeleton/ai/.env.local',
                     'skeleton/ai/model.gguf','skeleton/ai/secrets/file.py',
                     'skeleton/ai/private_key.py','skeleton/ai/../../../etc/passwd',
                     '/skeleton/ai/a.py','skeleton/ai/x.py\x00evil'):
            with self.subTest(path=path),self.assertRaises(GitSourceError):git_path(path)

    def test_untracked_file_is_not_indexable(self):
        (self.code/'untracked.py').write_text('SNEAKY = True\n')
        with self.assertRaises(GitSourceError):self.index((self.item('untracked.py'),))

    def test_symlink_git_entry_not_source_blob(self):
        (self.code/'link.py').symlink_to(self.code/'source.py')
        self.git('add','.');self.git('commit','-qm','symlink')
        with self.assertRaises(GitSourceError):self.index((self.item('link.py'),),head=self.git('rev-parse','HEAD'))

    def test_commit_pin_must_be_full_hex(self):
        for commit in ('HEAD','main',self.head[:8],'abc','0'*39,'ff'*40):
            with self.subTest(commit=commit),self.assertRaises(GitSourceError):
                GitSource(self.repo,commit=commit)

    def test_invalid_secret_matches_but_no_echo(self):
        for raw in (b'-----BEGIN ' + b'PRIVATE KEY-----\nABC\n',
                    b'ghp_' + b'x'*30,b'AKIA' + b'X'*16,
                    b'api_key="'+b'q'*40+b'"'):
            with self.subTest(raw=raw[:8]),self.assertRaises(GitSourceError):
                require_publicly_indexable(raw)

    def test_secret_source_cannot_partially_import_batch(self):
        (self.code/'other.py').write_text('KEY = "ghp_'+'x'*36+'"\n')
        self.git('add','.');self.git('commit','-qm','bad secret')
        with self.assertRaises(GitSourceError):
            self.index((self.item(),self.item('other.py')),head=self.git('rev-parse','HEAD'))
        self.assertFalse(self.plane.list())

    def test_batch_multi_file_atomic(self):
        rows=self.index((self.item(),self.item('other.py')))
        self.assertEqual(len(rows),2)
        self.assertEqual(inspect_repository(self.plane,repo_root=self.repo)['verified'],2)

    def test_batch_duplicate_paths_not_written(self):
        with self.assertRaises(GitSourceError):self.index((self.item(),self.item()))
        self.assertEqual(self.plane.list(),())

    def test_import_requires_approval(self):
        with self.assertRaises(GitSourceError):
            index_repository(self.plane,repo_root=self.repo,commit=self.head,
                             items=[self.item()],approved=False)

    def test_import_replay_requires_same_git_commit_and_blob(self):
        self.index()
        self.assertTrue(self.index()[0]['replayed'])
        (self.code/'other.py').write_text('OTHER = "updated"\n')
        self.git('add','.');self.git('commit','-qm','unrelated changed')
        # Original blob content matches, but the caller must not recertify it
        # under a different Git commit without an explicit provenance change.
        with self.assertRaises(GitSourceError):
            self.index((self.item(revision=1),),head=self.git('rev-parse','HEAD'))

    def test_indexed_git_commit_not_available_in_other_repo(self):
        self.index()
        other=self.root/'unrelated';other.mkdir(mode=0o700)
        subprocess.run(['git','-C',str(other),'init','-q'],check=True)
        with self.assertRaises(GitSourceError):
            inspect_repository(self.plane,repo_root=other)

    def test_lineage_tamper_is_detected(self):
        self.index()
        with self.db.transaction() as c:
            c.execute("UPDATE ai_kb_git_lineage SET blob_oid=?",('0'*40,))
        with self.assertRaises(GitSourceError):inspect_repository(self.plane,repo_root=self.repo)

    def test_model_or_principal_scope_prevents_cross_index_adoption(self):
        self.index()
        with self.db.snapshot() as c:
            self.assertFalse(c.execute('SELECT 1 FROM ai_kb_git_lineage WHERE principal=?',
                 (Identity('tenant','someone_else',M,T).key(),)).fetchone())

    def test_bounded_git_inventory_fails_closed(self):
        with self.assertRaises(GitSourceError):
            GitSource(self.repo,commit=self.head,maximum_paths=1).inventory()

    def test_bound_blob_size_checked_before_read(self):
        g=GitSource(self.repo,commit=self.head)
        with self.assertRaises(GitSourceError):g.read(self.item().path,g.inventory(),maximum_bytes=10)

    def test_read_only_git_doctor_does_not_mutate_db(self):
        self.index()
        before=self.plane.doctor()['proof_sha256']
        inspect_repository(self.plane,repo_root=self.repo)
        self.assertEqual(before,self.plane.doctor()['proof_sha256'])

    def test_cli_manifest_requires_exact_commit_and_identity(self):
        local=self.root/'operator-manifest';local.mkdir(mode=0o700)
        manifest={'schema':'skeleton.ai.exact-Git-sources.v1','commit_sha':self.head,
                  'sources':[{'path':self.item().path,'expected_revision':0,'rights':'operator-authored'}]}
        (local/'manifest.json').write_text(json.dumps(manifest),encoding='utf8')
        common=['--state-dir',str(self.state),'--repo-root',str(self.repo),
             '--tenant','tenant','--subject','reader','--model-sha256',M,
             '--tokenizer-sha256',T]
        self.assertEqual(cli(common+['ingest','--commit',self.head,'--manifest-root',str(local),
                            '--manifest','manifest.json']),2)
        self.assertEqual(cli(common+['ingest','--commit',self.head,'--manifest-root',str(local),
                            '--manifest','manifest.json','--approve-ingest']),0)
        self.assertEqual(cli(common+['doctor']),0)
        self.assertEqual(cli(common[:6]+['--subject','other',
               '--model-sha256',M,'--tokenizer-sha256',T,'doctor']),2)

if __name__=='__main__':unittest.main()
