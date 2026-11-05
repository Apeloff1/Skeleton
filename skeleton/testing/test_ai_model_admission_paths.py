"""Descriptor, permission, persistence and policy-failure fixtures."""
from __future__ import annotations
import os
from pathlib import Path
import tempfile
import unittest
from skeleton.ai.runtime.operational_ai.model.admission.paths import verified_dir,open_file,read_file,write_file
from skeleton.ai.runtime.operational_ai.model.admission.contracts import AdmissionCorrupt,AdmissionError
from skeleton.ai.runtime.operational_ai.model.admission.canonical import canonical,parse
from skeleton.ai.runtime.operational_ai.model.admission.proc import process_start_tick

class PathTests(unittest.TestCase):
    def setUp(self):
        ctx=tempfile.TemporaryDirectory();self.addCleanup(ctx.cleanup)
        self.root=Path(ctx.name)/'sealed';self.root.mkdir(mode=0o700)

    def test_private_root(self):
        fd=verified_dir(self.root);os.close(fd)

    def test_missing_directory_refused(self):
        with self.assertRaises(OSError):verified_dir(self.root/'missing')

    def test_symlink_parent_refused(self):
        (self.root/'linked').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(OSError):verified_dir(self.root/'linked')

    def test_dotdot_explicitly_rejected(self):
        with self.assertRaises(AdmissionError):verified_dir(str(self.root)+'/../sealed')

    def test_private_regular_file_and_repeat_reads(self):
        rootfd=verified_dir(self.root)
        try:
            fd=open_file(rootfd,'token.lock',create=True)
            try:
                write_file(fd,b'a'*4000)
                self.assertEqual(read_file(fd),b'a'*4000)
                write_file(fd,b'b'*5)
                self.assertEqual(read_file(fd),b'b'*5)
            finally:os.close(fd)
        finally:os.close(rootfd)

    def test_file_name_traversal_and_control_refused(self):
        rootfd=verified_dir(self.root)
        try:
            for filename in ('../x','x/y','x\\y','.', '', 'a\x00b'):
                with self.subTest(name=filename),self.assertRaises(AdmissionError):
                    open_file(rootfd,filename,create=True)
        finally:os.close(rootfd)

    def test_oversized_record_refused_without_allocating_more(self):
        fd=os.open(self.root/'large',os.O_CREAT|os.O_RDWR,0o600)
        try:
            os.write(fd,b'X'*16385)
            with self.assertRaises(AdmissionCorrupt):read_file(fd)
        finally:os.close(fd)

    def test_unknown_canonical_source_types_refused(self):
        for bad in (b'[]',b'null',b'{"a":NaN}',b'{"a":Infinity}'):
            with self.subTest(raw=bad),self.assertRaises(AdmissionCorrupt):parse(bad)

    def test_unicode_serialized_ascii_canonical(self):
        b=canonical({'note':'Électricité'})
        self.assertTrue(b.isascii())
        self.assertEqual(parse(b),{'note':'Électricité'})

    def test_process_stat_missing_or_malformed_refused(self):
        p=self.root/'100';p.mkdir()
        (p/'stat').write_text('100 (weird (comm)) bad\n')
        with self.assertRaises(AdmissionCorrupt):process_start_tick(100,self.root)

if __name__=='__main__':unittest.main()
