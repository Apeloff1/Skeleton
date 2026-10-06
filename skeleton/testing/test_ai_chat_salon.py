"""Salon conversation choreography — qualification."""

from __future__ import annotations

import unittest

from skeleton.ai.assistant.salon import (
    BeatKind,
    CitationChip,
    DiscourseAct,
    PresenceLamp,
    Reaction,
    SalonError,
    SalonPolicy,
    SalonSession,
    classify_act,
    surface_contract,
)


class SalonChoreographyTest(unittest.TestCase):
    def test_act_taxonomy(self) -> None:
        self.assertEqual(classify_act("hello there"), DiscourseAct.GREETING)
        self.assertEqual(classify_act("why is the lamp gold?"), DiscourseAct.ASK)
        self.assertEqual(classify_act("no, I meant the composer"), DiscourseAct.REPAIR)
        self.assertEqual(classify_act("prove that claim"), DiscourseAct.CHALLENGE)

    def test_conversation_is_not_a_single_blob(self) -> None:
        salon = SalonSession("thread-salon", policy=SalonPolicy(adage_gap=0))
        plan = salon.compose(
            "how should the chat feel in October?",
            body="Beats, not a bubble. Ingress, stance, body, adage, open hand.",
            chips=(CitationChip("c1", "salon law", "skeleton://ai/assistant/salon"),),
        )
        kinds = [beat.kind for beat in plan.beats]
        self.assertEqual(kinds[0], BeatKind.PRESENCE)
        self.assertIn(BeatKind.INGRESS, kinds)
        self.assertIn(BeatKind.STANCE, kinds)
        self.assertIn(BeatKind.BODY, kinds)
        self.assertIn(BeatKind.ADAGE, kinds)
        self.assertIn(BeatKind.OPEN_HAND, kinds)
        self.assertEqual(kinds[-1], BeatKind.SEAL)
        self.assertGreaterEqual(len(kinds), 6)
        self.assertEqual(plan.card.stored_prose, 0)
        self.assertFalse(plan.card.production_authority)
        self.assertTrue(plan.card.adage_fired)
        body = next(beat for beat in plan.beats if beat.kind is BeatKind.BODY)
        self.assertEqual(len(body.chips), 1)

    def test_user_prose_is_not_in_the_ledger(self) -> None:
        secret = "the user said a very specific private sentence about fjords"
        salon = SalonSession("thread-ledger")
        plan = salon.compose(secret, body="ack")
        ledger = salon.ledger()
        blob = str(plan.as_dict()) + str(ledger)
        self.assertNotIn(secret, blob)
        self.assertEqual(ledger["stored_prose"], 0)
        self.assertEqual(plan.user_pointer, salon.hear_pointer(secret))

    def test_adage_respects_gap_and_heat(self) -> None:
        salon = SalonSession("thread-gap", policy=SalonPolicy(adage_gap=2))
        first = salon.compose("what is the seam?", body="one")
        self.assertFalse(first.card.adage_fired)
        second = salon.compose("and the next cut?", body="two")
        self.assertFalse(second.card.adage_fired)
        third = salon.compose("continue the spec", body="three")
        self.assertTrue(third.card.adage_fired)
        heated = SalonSession("thread-heat", policy=SalonPolicy(adage_gap=0))
        hot = heated.compose("this is useless again", body="short")
        self.assertFalse(hot.card.adage_fired)
        self.assertEqual(hot.card.affect, "heated")

    def test_interrupt_drops_the_tail(self) -> None:
        salon = SalonSession("thread-cut", policy=SalonPolicy(adage_gap=0))
        plan = salon.compose("what next?", body="long body")
        body_seq = next(beat.seq for beat in plan.beats if beat.kind is BeatKind.BODY)
        cut = salon.interrupt(body_seq)
        visible = cut.visible()
        self.assertEqual(visible[-1].kind, BeatKind.BODY)
        self.assertNotIn(BeatKind.SEAL, [beat.kind for beat in visible])
        self.assertEqual(salon.lamp, PresenceLamp.INTERRUPTED)
        self.assertEqual(salon.interruptions, 1)

    def test_presence_beat_cannot_be_cut(self) -> None:
        salon = SalonSession("thread-presence")
        salon.compose("hello", body="here")
        with self.assertRaises(SalonError):
            salon.interrupt(0)

    def test_callback_on_repeated_grain(self) -> None:
        salon = SalonSession("thread-motif", policy=SalonPolicy(adage_gap=9))
        salon.compose("the composer rearm contract", body="first")
        second = salon.compose("the composer rearm contract again", body="second")
        self.assertIsNotNone(second.card.callback_motif)
        self.assertTrue(any(beat.kind is BeatKind.CALLBACK for beat in second.beats))

    def test_quieter_reaction_closes_the_open_hand(self) -> None:
        salon = SalonSession("thread-react", policy=SalonPolicy(adage_gap=0, max_open_hands=1))
        salon.compose("how does pin work?", body="pin stores the motif id")
        salon.react(Reaction.QUIETER)
        nxt = salon.compose("and fork?", body="fork retargets the thread pointer")
        self.assertNotIn(BeatKind.OPEN_HAND, [beat.kind for beat in nxt.beats])
        self.assertFalse(nxt.card.adage_fired)

    def test_replay_is_deterministic(self) -> None:
        def run() -> str:
            salon = SalonSession("thread-replay", policy=SalonPolicy(adage_gap=0, play_bias=0.4))
            plan = salon.compose("why cadence?", body="courtesy")
            return plan.card.digest

        self.assertEqual(run(), run())

    def test_reduced_motion_zeroes_cadence(self) -> None:
        salon = SalonSession("thread-motion", policy=SalonPolicy(reduced_motion=True))
        plan = salon.compose("hello", body="room")
        self.assertTrue(all(beat.cadence_ms == 0 for beat in plan.beats))

    def test_empty_body_still_converses(self) -> None:
        salon = SalonSession("thread-open")
        plan = salon.compose("still there?")
        body = next(beat for beat in plan.beats if beat.kind is BeatKind.BODY)
        self.assertIn("answer slot", body.text)
        self.assertIn(BeatKind.OPEN_HAND, [beat.kind for beat in plan.beats])

    def test_surface_contract(self) -> None:
        contract = surface_contract()
        self.assertEqual(contract["stored_prose"], 0)
        self.assertIn("/pin", contract["composer"]["slash"])
        self.assertTrue(contract["motion"]["focus_returns_to_composer"])


if __name__ == "__main__":
    unittest.main()
