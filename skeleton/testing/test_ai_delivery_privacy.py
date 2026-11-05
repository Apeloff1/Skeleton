"""Adversarial privacy schemas for independent on-device AI event consumers."""
from __future__ import annotations
import copy, unittest
from hashlib import sha256
from skeleton.ai.runtime.operational_ai.transport.flight.outbox_delivery.schema import validate_external
from skeleton.ai.runtime.operational_ai.transport.flight.outbox_delivery.contracts import DeliveryHeld

D='a'*64

def flight(kind='submitted',fields=None):
    if fields is None:fields={'principal':'a'*64,'request_sha256':D,'priority':1}
    return {'sequence':1,'event_key':'flight_abc','stream':'job1','kind':'ai_flight',
            'event_sha256':D,'payload':{'schema':'skeleton.ai.flight-event.v1',
            'job_id':'job1','ordinal':1,'kind':kind,'fields':fields,'prior_digest':'0'*64}}

def turn():
    return {'sequence':2,'event_key':'turn_s1_r1','stream':'s1','kind':'ai_turn',
            'event_sha256':D,'payload':{'schema':'spine.turn.v1','session':'s1',
            'request_id':'r1','revision':1,'request_sha256':D,'output_sha256':D,
            'model_sha256':D,'tokenizer_sha256':D,'prompt_tokens':10,
            'generated_tokens':6,'finish_reason':'stop','principal':'a'*64,
            'context_sha256':D,'omitted_turns':0,'evidence_refs':[]}}

class ExternalDeliverySchemaTests(unittest.TestCase):
    def test_known_flight(self):validate_external(flight())
    def test_known_turn(self):validate_external(turn())
    def test_unknown_kind_blocks(self):
        r=flight();r['payload']['kind']='run-shell'
        self.assertRaises(DeliveryHeld,validate_external,r)
    def test_flight_fields_exact(self):
        for added in ('content','prompt','metadata','response','api_key','random'):
            with self.subTest(added=added):
                r=flight();r['payload']['fields'][added]='secret'
                self.assertRaises(DeliveryHeld,validate_external,r)
    def test_flight_submitted_priority_range(self):
        for value in (-1,10,True,'1'):
            with self.subTest(value=value):
                r=flight();r['payload']['fields']['priority']=value
                self.assertRaises(DeliveryHeld,validate_external,r)
    def test_flight_stale_stream_refused(self):
        r=flight();r['stream']='job2'
        self.assertRaises(DeliveryHeld,validate_external,r)
    def test_wrong_model_turn_field_refused(self):
        r=turn();r['payload']['model_sha256']='invalid'
        self.assertRaises(DeliveryHeld,validate_external,r)
    def test_empty_turn_finish_reason_rejected(self):
        r=turn();r['payload']['finish_reason']='function_call'
        self.assertRaises(DeliveryHeld,validate_external,r)
    def test_untrusted_turn_unknown_field_refused(self):
        for field in ('answer','response','tool_result','messages','source_text','question'):
            with self.subTest(field=field):
                r=turn();r['payload'][field]='private'
                self.assertRaises(DeliveryHeld,validate_external,r)
    def test_source_reference_identity_and_sha(self):
        r=turn();r['payload']['evidence_refs']=[{'id':'source1','revision':1,
            'passage_sha256':D,'document_sha256':None}]
        validate_external(r)
        r['payload']['evidence_refs'][0]['content']='secret'
        self.assertRaises(DeliveryHeld,validate_external,r)
    def test_turn_true_boolean_metric_refused(self):
        r=turn();r['payload']['prompt_tokens']=True
        self.assertRaises(DeliveryHeld,validate_external,r)
    def test_invalid_raw_identifier_refused(self):
        r=flight();r['event_key']='job/../secret'
        self.assertRaises(DeliveryHeld,validate_external,r)
    def test_completed_receipt_hash_only(self):
        r=flight('completed',{'receipt_sha256':D})
        validate_external(r)
        r['payload']['fields']['output']='text'
        self.assertRaises(DeliveryHeld,validate_external,r)
    def test_unknown_root_export_field_refused(self):
        r=flight();r['license']='unknown'
        self.assertRaises(DeliveryHeld,validate_external,r)
    def test_future_capacity_schema_must_be_reviewed(self):
        r=turn();r['payload']['context_capacity']={'next_schema':'future'}
        self.assertRaises(DeliveryHeld,validate_external,r)
    def test_nonfinite_field_rejected(self):
        r=flight();r['payload']['fields']['priority']=float('nan')
        self.assertRaises(DeliveryHeld,validate_external,r)

if __name__=='__main__':unittest.main()
