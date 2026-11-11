"""Fixture-only first boot and replay: never claim a real GGUF qualification."""
import copy,errno,hashlib,json,os,stat,tempfile,unittest
from pathlib import Path
from contextlib import ExitStack
from unittest import mock
from skeleton.ai.runtime.operational_ai.deployment.qualification import (
    QualificationInput,QualificationError,probe_first_boot,
)
from skeleton.ai.runtime.operational_ai.deployment.qualification.verification import verify
from skeleton.ai.runtime.operational_ai.deployment.qualification import verification as receipt_verification
from skeleton.ai.runtime.operational_ai.deployment.qualification.proof import construct
from skeleton.ai.runtime.operational_ai.deployment.qualification.paths import publish_private_report
from skeleton.ai.runtime.operational_ai.deployment.qualification import paths as report_paths
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import (
    SpineDatabase, ExecutionSpine, Identity, SpineLimits,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.ai.runtime.operational_ai.model.native import Generated

I=Identity('team','owner','a'*64,'b'*64)

class ProbeBackend:
    model_digest=I.model_sha256
    tokenizer_digest=I.tokenizer_sha256
    def __init__(self,counters):self.counters=counters
    def generate(self,messages,*,max_output_tokens,seed,temperature):
        self.counters['generated']+=1
        text='Native fixture response'
        return Generated(text,60,5,hashlib.sha256(text.encode()).hexdigest(),
                         self.model_digest,self.tokenizer_digest,'stop')

class QualificationTests(unittest.TestCase):
    def setUp(self):
        # GGUF descriptor custody checks every ancestor; /tmp is 01777.
        # Use a per-test 0700 directory under the non-group-writable home.
        self.tmp=tempfile.TemporaryDirectory(dir=Path.home())
        self.state=Path(self.tmp.name)/'private'
        self.state.mkdir(mode=0o700)
        self.out=Path(self.tmp.name)/'reports';self.out.mkdir(mode=0o700)
        self.counter={'generated':0}
        self.plan=QualificationInput(Path(self.tmp.name)/'model',self.state,
                                     'team','owner')
    def tearDown(self):self.tmp.cleanup()
    def factory(self,**kwargs):
        stack=ExitStack()
        db=stack.enter_context(SpineDatabase(self.state))
        lock=self.state/'lock'
        lock.mkdir(mode=0o700,exist_ok=True)
        gate=stack.enter_context(SessionGate(lock))
        spine=ExecutionSpine(db=db,session_gate=gate,
            backend=ProbeBackend(self.counter),identity=I,
            limits=SpineLimits(max_output_tokens=64,context_tokens=2048))
        return stack,SupervisedAI(spine)

    def test_reboot_replay_executes_native_fixture_once(self):
        proof=probe_first_boot(self.plan,activation=self.factory)
        self.assertEqual(proof['status'],'fixture-only-not-production-certified')
        self.assertEqual(self.counter['generated'],1)
        self.assertEqual(proof['database_turns'],1)
        self.assertEqual(verify(proof,require_real=False)['real_model_executed'],False)
        with self.assertRaisesRegex(QualificationError,'fixture'):
            verify(proof)

    def test_proof_records_no_source_prompt_or_model_output(self):
        proof=probe_first_boot(self.plan,activation=self.factory)
        result=json.dumps(proof)
        self.assertNotIn('Native fixture response',result)
        self.assertNotIn('offline model should preserve',result)
        self.assertNotIn(self.tmp.name,result)

    def test_proof_tampering_detected(self):
        proof=probe_first_boot(self.plan,activation=self.factory)
        changed=copy.deepcopy(proof);changed['generated_tokens']=1234
        with self.assertRaisesRegex(QualificationError,'digest mismatch'):
            verify(changed,require_real=False)

    def test_verify_rejects_unbounded_or_non_first_boot_numeric_evidence(self):
        proof = probe_first_boot(self.plan, activation=self.factory)
        bad_counters = (
            ('revision', 2),
            ('revision', 1 << 100_000),
            ('database_turns', 2),
            ('database_turns', True),
            ('generated_tokens', 8193),
            ('generated_tokens', 1 << 100_000),
            ('prompt_tokens', 131073),
            ('prompt_tokens', -1),
        )
        for key, invalid in bad_counters:
            with self.subTest(key=key, invalid_bits=invalid.bit_length()
                              if type(invalid) is int else None):
                altered = dict(proof)
                altered[key] = invalid
                with mock.patch.object(
                    receipt_verification, 'canonical',
                    side_effect=AssertionError('invalid receipt serialized'),
                ):
                    with self.assertRaisesRegex(
                        QualificationError, 'invalid numeric qualification evidence',
                    ):
                        verify(altered, require_real=False)
        # The original bounded fixture receipt remains verifiable.
        self.assertFalse(verify(proof, require_real=False)['real_model_executed'])

    def test_verify_rejects_malformed_digests_as_qualification_errors(self):
        proof = probe_first_boot(self.plan, activation=self.factory)
        for invalid in ('G' * 64, 'a' * 63, '', None):
            with self.subTest(invalid=repr(invalid)):
                altered = dict(proof)
                altered['model_sha256'] = invalid
                with self.assertRaisesRegex(
                    QualificationError, 'invalid qualification digest',
                ):
                    verify(altered, require_real=False)

    def test_construct_rejects_forged_first_boot_evidence_before_hashing(self):
        answer = 'fixture reply'
        digest = hashlib.sha256(answer.encode('utf8')).hexdigest()
        first = {
            'replayed': False, 'revision': 1,
            'output_sha256': digest, 'request_sha256': 'a' * 64,
            'context_sha256': 'b' * 64,
            'generated_tokens': 2, 'prompt_tokens': 4,
        }
        replayed = dict(first, replayed=True)
        history = ({'role': 'user', 'content': 'hi'},
                   {'role': 'assistant', 'content': answer})
        diagnostics = {'turns': 1}

        def issue(first_receipt=first, replay_receipt=replayed,
                  doctor=diagnostics, model='c' * 64):
            return construct(model, 'd' * 64, 'session', 'request',
                             first_receipt, replay_receipt, history, doctor,
                             exact_native=False)

        self.assertFalse(verify(issue(), require_real=False)['real_model_executed'])
        malformed = (
            (dict(first, revision=True), replayed, diagnostics, 'c' * 64),
            (first, dict(replayed, revision=True), diagnostics, 'c' * 64),
            (first, replayed, {'turns': True}, 'c' * 64),
            (dict(first, generated_tokens=1 << 100_000), replayed,
             diagnostics, 'c' * 64),
            (dict(first, prompt_tokens=131073), replayed, diagnostics,
             'c' * 64),
            (dict(first, request_sha256='bad'),
             dict(replayed, request_sha256='bad'), diagnostics, 'c' * 64),
            (dict(first, context_sha256='bad'), replayed, diagnostics,
             'c' * 64),
            (first, replayed, diagnostics, 'not-a-sha'),
        )
        for index, (receipt, replay, doctor, model) in enumerate(malformed):
            with self.subTest(index=index):
                with self.assertRaises(QualificationError):
                    issue(receipt, replay, doctor, model)

    def test_same_report_filename_never_overwrites(self):
        proof=probe_first_boot(self.plan,activation=self.factory)
        publish_private_report(self.out,'report.json',proof)
        before=(self.out/'report.json').read_bytes()
        with self.assertRaises(FileExistsError):
            publish_private_report(self.out,'report.json',proof)
        self.assertEqual((self.out/'report.json').read_bytes(),before)
        self.assertEqual((self.out/'report.json').stat().st_mode & 0o777,0o600)
        self.assertEqual([p.name for p in self.out.iterdir()], ['report.json'])
        self.assertEqual((self.out/'report.json').stat().st_nlink, 1)

    def test_report_parent_permissions_hold(self):
        proof=probe_first_boot(self.plan,activation=self.factory)
        os.chmod(self.out,0o755)
        with self.assertRaises(QualificationError):
            publish_private_report(self.out,'report.json',proof)

    def test_report_rejects_control_unicode_and_oversized_names(self):
        bad_names = (
            'line\nbreak.json', 'line\rbreak.json', 'tab\t.json',
            'nul\x00.json', 'unicode-\u2603.json', 'rtl-\u202e.json',
            'bad name.json', 'a' * 96 + '.json',
        )
        for name in bad_names:
            with self.subTest(name=repr(name)), self.assertRaises(QualificationError):
                publish_private_report(self.out, name, {'schema': 'fixture-only'})
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_streaming_keeps_canonical_bytes(self):
        payload = {'z': 'café', 'a': {'nested': [1, True, None]}}
        name = 'a' * 95 + '.json'
        publish_private_report(self.out, name, payload)
        expected = (json.dumps(payload, sort_keys=True, separators=(',', ':'),
                               allow_nan=False, ensure_ascii=True) + '\n').encode('utf8')
        self.assertEqual((self.out / name).read_bytes(), expected)
        self.assertEqual((self.out / name).stat().st_mode & 0o777, 0o600)

    def test_report_payload_rejections_leave_no_output(self):
        cyclic = {}
        cyclic['self'] = cyclic
        for index, payload in enumerate((
            {'value': object()},
            {'value': float('nan')},
            {'value': float('inf')},
            cyclic,
        )):
            with self.subTest(index=index), self.assertRaisesRegex(
                QualificationError, 'invalid qualification report payload',
            ):
                publish_private_report(self.out, 'bad.json', payload)
            self.assertFalse((self.out / 'bad.json').exists())

    def test_report_requires_object_payload_before_filesystem_io(self):
        for payload in (None, True, 'signed', 42, [], [1, 2]):
            with self.subTest(payload=repr(payload)), self.assertRaisesRegex(
                QualificationError, 'invalid qualification report payload',
            ):
                publish_private_report(self.out, 'scalar.json', payload)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_large_string_preflight_never_invokes_json_encoder(self):
        payload = {'text': 'x' * (report_paths._MAX_REPORT_BYTES * 128)}
        with mock.patch.object(
            report_paths.json.JSONEncoder, 'iterencode',
            side_effect=AssertionError('unbounded JSON chunk allocated'),
        ):
            with self.assertRaisesRegex(QualificationError, 'oversized'):
                publish_private_report(self.out, 'large-string.json', payload)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_escaped_unicode_preflight_never_allocates_json_chunk(self):
        # 1,500 non-BMP characters occupy 18,000 bytes after ensure_ascii.
        # The raw Python string is smaller than the 16,384-byte cap.
        payload = {'emoji': '\U0001f600' * 1500}
        self.assertLess(len(payload['emoji']), report_paths._MAX_REPORT_BYTES)
        with mock.patch.object(
            report_paths.json.JSONEncoder, 'iterencode',
            side_effect=AssertionError('oversized escaped chunk allocated'),
        ):
            with self.assertRaisesRegex(QualificationError, 'oversized'):
                publish_private_report(self.out, 'emoji.json', payload)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_escaped_ascii_preflight_never_allocates_json_chunk(self):
        for index, content in enumerate((
            '"' * 9000,
            '\x00' * 3000,
            '\u2028' * 3000,
        )):
            with self.subTest(index=index), mock.patch.object(
                report_paths.json.JSONEncoder, 'iterencode',
                side_effect=AssertionError('oversized escaped chunk allocated'),
            ):
                with self.assertRaisesRegex(QualificationError, 'oversized'):
                    publish_private_report(self.out, 'escaped.json', {'value': content})
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_nonstring_keys_rejected_before_json_encoder(self):
        # JSON silently coerces 1 and True to '1' and 'true'; this can
        # duplicate a string key and make receipt interpretation ambiguous.
        for index, payload in enumerate((
            {1: 'numeric'},
            {None: 'null'},
            {'nested': {'true': 'trusted', True: 'untrusted'}},
        )):
            with self.subTest(index=index), mock.patch.object(
                report_paths.json.JSONEncoder, 'iterencode',
                side_effect=AssertionError('ambiguous JSON keys encoded'),
            ):
                with self.assertRaisesRegex(
                    QualificationError, 'invalid qualification report payload',
                ):
                    publish_private_report(self.out, 'keys.json', payload)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_bounded_unicode_and_escapes_preserve_canonical_bytes(self):
        payload = {'emoji': '\U0001f600' * 12, 'controls': '\x00\n\t',
                   'quoted': '"\\', 'nested': {'café': True}}
        publish_private_report(self.out, 'unicode.json', payload)
        expected = (json.dumps(payload, sort_keys=True, separators=(',', ':'),
                               allow_nan=False, ensure_ascii=True) + '\n').encode('ascii')
        self.assertEqual((self.out / 'unicode.json').read_bytes(), expected)

    def test_report_large_container_preflight_never_invokes_json_encoder(self):
        payload = {'entries': [None] * (report_paths._MAX_REPORT_BYTES + 1)}
        with mock.patch.object(
            report_paths.json.JSONEncoder, 'iterencode',
            side_effect=AssertionError('unbounded JSON container encoded'),
        ):
            with self.assertRaisesRegex(QualificationError, 'oversized'):
                publish_private_report(self.out, 'large-list.json', payload)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_huge_integer_preflight_never_invokes_json_encoder(self):
        payload = {'counter': 1 << (report_paths._MAX_REPORT_BYTES * 5)}
        with mock.patch.object(
            report_paths.json.JSONEncoder, 'iterencode',
            side_effect=AssertionError('unbounded integer encoded'),
        ):
            with self.assertRaisesRegex(QualificationError, 'oversized'):
                publish_private_report(self.out, 'huge-int.json', payload)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_cyclic_preflight_rejects_without_json_recursion(self):
        payload = {}
        payload['cycle'] = payload
        with mock.patch.object(
            report_paths.json.JSONEncoder, 'iterencode',
            side_effect=AssertionError('recursive JSON encoder entered'),
        ):
            with self.assertRaisesRegex(QualificationError, 'invalid qualification report payload'):
                publish_private_report(self.out, 'cycle.json', payload)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_byte_budget_rejected_before_publication(self):
        with self.assertRaisesRegex(QualificationError, 'oversized'):
            publish_private_report(self.out, 'oversized.json',
                                   {'data': 'x' * 1_000_000})
        self.assertFalse((self.out / 'oversized.json').exists())

    def test_writable_nonsticky_report_ancestor_rejected(self):
        root = Path(self.tmp.name) / 'shared'
        root.mkdir(mode=0o700)
        os.chmod(root, 0o777)
        child = root / 'private'
        child.mkdir(mode=0o700)
        with self.assertRaises(QualificationError):
            publish_private_report(child, 'receipt.json', {'status': 'fixture-only'})
        self.assertFalse((child / 'receipt.json').exists())

    def test_report_short_write_retries_before_atomic_publication(self):
        real_write = os.write
        calls = [0]

        def short_first(fd, data):
            calls[0] += 1
            if calls[0] == 1:
                return real_write(fd, data[:1])
            return real_write(fd, data)

        payload = {'a': 'bounded'}
        with mock.patch.object(report_paths.os, 'write', side_effect=short_first):
            publish_private_report(self.out, 'short.json', payload)
        expected = (json.dumps(payload, sort_keys=True, separators=(',', ':'),
                               allow_nan=False, ensure_ascii=True) + '\n').encode('ascii')
        self.assertEqual((self.out / 'short.json').read_bytes(), expected)
        self.assertGreaterEqual(calls[0], 2)
        self.assertEqual([p.name for p in self.out.iterdir()], ['short.json'])

    def test_report_zero_byte_write_does_not_publish_receipt(self):
        with mock.patch.object(report_paths.os, 'write', return_value=0):
            with self.assertRaisesRegex(QualificationError, 'cannot write'):
                publish_private_report(self.out, 'zero.json', {'ok': True})
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_fsync_failure_leaves_no_partial_final_or_stage(self):
        with mock.patch.object(report_paths.os, 'fsync',
                               side_effect=OSError(errno.ENOSPC, 'disk full')):
            with self.assertRaises(OSError):
                publish_private_report(self.out, 'partial.json', {'ok': True})
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_directory_fsync_failure_rolls_back_final_name(self):
        real_fsync = os.fsync
        calls = [0]

        def fail_second(fd):
            calls[0] += 1
            if calls[0] == 2:
                raise OSError(errno.ENOSPC, 'directory sync failed')
            return real_fsync(fd)

        with mock.patch.object(report_paths.os, 'fsync', side_effect=fail_second):
            with self.assertRaises(OSError):
                publish_private_report(self.out, 'not-committed.json', {'ok': True})
        self.assertEqual(calls[0], 2)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_parent_replacement_after_link_rolls_back_receipt(self):
        real_open = report_paths._open_private_report_root
        calls = [0]

        def reject_third(root):
            calls[0] += 1
            if calls[0] == 3:
                raise QualificationError('report parent changed during publication')
            return real_open(root)

        with mock.patch.object(report_paths, '_open_private_report_root',
                               side_effect=reject_third):
            with self.assertRaisesRegex(QualificationError, 'parent changed'):
                publish_private_report(self.out, 'wrong-parent.json', {'ok': True})
        self.assertEqual(calls[0], 3)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_stage_descriptor_remains_pinned_through_final_check(self):
        """Unlinked published inode cannot be recycled during rollback."""
        real_os_open = report_paths.os.open
        real_root_open = report_paths._open_private_report_root
        stage_fd = [None]
        root_calls = [0]

        def track_stage(path, flags, *args, **kwargs):
            handle = real_os_open(path, flags, *args, **kwargs)
            # Capture the *writer* descriptor, not the temporary reader
            # opened by _require_our_name. That reader is closed after its
            # identity check, while the writer must remain pinned through
            # post-link verification and rollback.
            if (type(path) is str and path.startswith('.qualification-')
                    and path.endswith('.tmp') and flags & os.O_CREAT):
                self.assertIsNone(stage_fd[0])
                stage_fd[0] = handle
            return handle

        def inspect_third(root):
            root_calls[0] += 1
            if root_calls[0] == 3:
                self.assertIsNotNone(stage_fd[0])
                pinned = os.fstat(stage_fd[0])
                self.assertTrue(stat.S_ISREG(pinned.st_mode))
                self.assertEqual(pinned.st_nlink, 1)
            return real_root_open(root)

        with mock.patch.object(report_paths.os, 'open', side_effect=track_stage):
            with mock.patch.object(report_paths, '_open_private_report_root',
                                   side_effect=inspect_third):
                publish_private_report(self.out, 'pinned.json', {'ok': True})
        self.assertEqual(root_calls[0], 3)
        self.assertEqual((self.out / 'pinned.json').read_bytes(), b'{"ok":true}\n')
        with self.assertRaises(OSError):
            os.fstat(stage_fd[0])

    def test_report_replaced_after_link_is_not_accepted_or_deleted(self):
        real_open = report_paths._open_private_report_root
        calls = [0]
        forged = b'foreign receipt must survive failed publication'

        def replace_on_third(root):
            calls[0] += 1
            if calls[0] == 3:
                target = self.out / 'replaced.json'
                target.unlink()
                target.write_bytes(forged)
            return real_open(root)

        with mock.patch.object(report_paths, '_open_private_report_root',
                               side_effect=replace_on_third):
            with self.assertRaisesRegex(QualificationError, 'identity changed'):
                publish_private_report(self.out, 'replaced.json', {'ok': True})
        self.assertEqual((self.out / 'replaced.json').read_bytes(), forged)
        self.assertEqual([p.name for p in self.out.iterdir()], ['replaced.json'])

    def test_report_stage_content_mutation_is_rejected_before_link(self):
        real_open = report_paths._open_private_report_root
        calls = [0]

        def mutate_second(root):
            calls[0] += 1
            if calls[0] == 2:
                stages = list(self.out.glob('.qualification-*.tmp'))
                self.assertEqual(len(stages), 1)
                original = stages[0].read_bytes()
                stages[0].write_bytes(b'X' * len(original))
            return real_open(root)

        with mock.patch.object(report_paths, '_open_private_report_root',
                               side_effect=mutate_second):
            with self.assertRaisesRegex(QualificationError, 'contents changed'):
                publish_private_report(self.out, 'stage-tampered.json', {'ok': True})
        self.assertEqual(calls[0], 2)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_in_place_post_link_rewrite_is_not_attested(self):
        real_open = report_paths._open_private_report_root
        calls = [0]

        def rewrite_third(root):
            calls[0] += 1
            if calls[0] == 3:
                target = self.out / 'rewritten.json'
                original = target.read_bytes()
                # Keep the inode, file length and mode unchanged: dev/ino
                # checks alone cannot detect this forged canonical receipt.
                target.write_bytes(b'X' * len(original))
            return real_open(root)

        with mock.patch.object(report_paths, '_open_private_report_root',
                               side_effect=rewrite_third):
            with self.assertRaisesRegex(QualificationError, 'contents changed'):
                publish_private_report(self.out, 'rewritten.json', {'ok': True})
        self.assertEqual(calls[0], 3)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_post_link_mode_relaxation_is_rejected(self):
        real_open = report_paths._open_private_report_root
        calls = [0]

        def relax_third(root):
            calls[0] += 1
            if calls[0] == 3:
                os.chmod(self.out / 'relaxed.json', 0o644)
            return real_open(root)

        with mock.patch.object(report_paths, '_open_private_report_root',
                               side_effect=relax_third):
            with self.assertRaisesRegex(QualificationError, 'identity changed'):
                publish_private_report(self.out, 'relaxed.json', {'ok': True})
        self.assertEqual(calls[0], 3)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_report_post_link_extra_hardlink_is_not_attested(self):
        real_open = report_paths._open_private_report_root
        calls = [0]
        extra = self.out / 'extra-link.json'

        def link_third(root):
            calls[0] += 1
            if calls[0] == 3:
                os.link(self.out / 'linked.json', extra)
            return real_open(root)

        try:
            with mock.patch.object(report_paths, '_open_private_report_root',
                                   side_effect=link_third):
                with self.assertRaisesRegex(QualificationError, 'identity changed'):
                    publish_private_report(self.out, 'linked.json', {'ok': True})
            self.assertEqual(calls[0], 3)
            self.assertFalse((self.out / 'linked.json').exists())
            # Do not remove another writer's link during rollback.
            self.assertTrue(extra.exists())
            self.assertEqual(extra.stat().st_nlink, 1)
        finally:
            extra.unlink(missing_ok=True)

    def test_report_name_traversal_refused(self):
        proof=probe_first_boot(self.plan,activation=self.factory)
        for name in ('../escape.json','/tmp/x.json','.json','bad.txt'):
            with self.subTest(name=name),self.assertRaises(QualificationError):
                publish_private_report(self.out,name,proof)

    def test_second_restart_with_mismatched_identity_fails(self):
        count=[0]
        def factory(**kwargs):
            count[0]+=1
            stack,worker=self.factory(**kwargs)
            if count[0]==2:worker.spine.identity=Identity('foreign','owner','a'*64,'b'*64)
            return stack,worker
        with self.assertRaises(QualificationError):
            probe_first_boot(self.plan,activation=factory)

    def test_no_real_checkpoint_is_reported_by_fixture(self):
        result=probe_first_boot(self.plan,activation=self.factory)
        self.assertEqual(result['checkpoint_execution_mode'],'injected-test-double')

if __name__=='__main__':unittest.main()
