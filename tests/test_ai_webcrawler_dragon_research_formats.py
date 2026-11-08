"""Bounded research-artifact parsers: positive and adversarial source tests."""
from __future__ import annotations

import json
import unittest

from skeleton.ai.webcrawler.research_projection import ResearchFormatError
from skeleton.ai.webcrawler.research_artifacts import RESEARCH_ARTIFACT_TYPES, extract_research_artifact
from skeleton.ai.webcrawler.timed_media import extract_timed_media
from skeleton.ai.webcrawler.calendar_documents import extract_calendar
from skeleton.ai.webcrawler.notebook_documents import extract_notebook
from skeleton.ai.webcrawler.bibliography_documents import extract_ris, extract_bibtex
from skeleton.ai.webcrawler.rdf_documents import extract_rdf_lines

VTT = ("WEBVTT\n\nNOTE https://outside.example.net/hidden\n\n"
       "00:00:01.000 --> 00:00:03.250\n<v Pilot>Wing loading and flight dynamics</v>\n\n"
       "00:00:04.000 --> 00:00:05.000 position:10%\nAirframe coefficient review\n")
SRT = ("1\n00:00:01,100 --> 00:00:02,200\nFirst bounded caption\n\n"
       "2\n00:00:03,100 --> 00:00:04,400\nSecond bounded caption\n")
ICS = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
       "SUMMARY:Flight dynamics symposium\r\nDTSTART;VALUE=DATE:20261107\r\n"
       "DESCRIPTION:Aircraft configuration seminar\r\n"
       "ATTENDEE:mailto:alice@example.com\r\nORGANIZER:mailto:bob@example.com\r\n"
       "ATTACH:https://outside.example.net/private\r\n"
       "BEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT10M\r\nEND:VALARM\r\n"
       "END:VEVENT\r\nEND:VCALENDAR\r\n")
RIS = ("TY  - JOUR\nTI  - Stability of archived flight models\nAU  - A. Researcher\n"
       "AB  - Wing force\n  and lift dynamics\nDO  - 10.1234/original\n"
       "UR  - https://outside.example.net/private\nER  -\n")
BIB = ("@article{flight2026, title={Flight stability observations},"
       " author={A. Researcher}, year={2026},"
       " abstract={Measured wing lift and airframe motion}, doi={10.1234/original} }\n")
NOTEBOOK = json.dumps({
    "nbformat": 4, "nbformat_minor": 5,
    "metadata": {"private": "SECRET_NONEXPORTED_METADATA"}, "cells": [
        {"cell_type": "markdown", "source": ["# Wing performance\n", "Flight dynamics analysis."]},
        {"cell_type": "code", "source": "angle_of_attack = 12\nprint('lift')",
         "execution_count": 9, "outputs": [{"text": "SECRET_OUTPUT"}]},
        {"cell_type": "code", "source": "api_key = 'SECRET_CODE_VALUE'", "outputs": []},
    ],
})
TRIPLES = ('<https://example.com/aircraft> <https://schema.org/name> '
           '"Original flight simulation"@en .\n')
QUADS = ('<https://example.com/s> <https://example.com/p> '
         '"value" <https://example.com/g> .\n')


class TimedMediaTests(unittest.TestCase):
    def test_webvtt_inert_timed_text(self):
        row = extract_timed_media(VTT, "text/vtt")
        self.assertIn("Wing loading", row.text)
        self.assertIn("00:00:03.250", row.text)
        self.assertNotIn("outside.example.net", row.text)
        self.assertEqual(row.links, ())
        self.assertFalse(row.body_executed)
        self.assertFalse(row.reference_trusted)

    def test_subrip_both_cues(self):
        row = extract_timed_media(SRT, "application/x-subrip")
        self.assertEqual(row.text.count("caption"), 2)

    def test_timestamp_overflow_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_timed_media("WEBVTT\n\n00:61.000 --> 00:62.000\nBad", "text/vtt")

    def test_reversed_interval_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_timed_media("WEBVTT\n\n00:05.000 --> 00:03.000\nBad", "text/vtt")

    def test_reverse_order_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_timed_media("WEBVTT\n\n00:05.000 --> 00:07.000\nA\n\n"
                                "00:01.000 --> 00:02.000\nB", "text/vtt")

    def test_missing_signature_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_timed_media(SRT, "text/vtt")

    def test_caption_markup_not_executed(self):
        row = extract_timed_media(
            "WEBVTT\n\n00:01.000 --> 00:02.000\n<script>alert(1)</script>Wing",
            "text/vtt",
        )
        self.assertEqual(row.links, ())
        self.assertFalse(row.body_executed)

    def test_cue_capacity_bound(self):
        with self.assertRaises(ResearchFormatError):
            extract_timed_media(
                "1\n00:00:00,000 --> 00:00:01,000\nA\n\n" * 1025,
                "application/x-subrip",
            )

    def test_text_truncation_advertised(self):
        row = extract_timed_media(VTT, "text/vtt", max_chars=32)
        self.assertTrue(row.truncated)
        self.assertEqual(len(row.text), 32)


class CalendarTests(unittest.TestCase):
    def test_event_retained_invitees_not_retained(self):
        row = extract_calendar(ICS)
        self.assertIn("Flight dynamics symposium", row.text)
        self.assertIn("20261107", row.text)
        self.assertNotIn("alice@example.com", row.text)
        self.assertNotIn("bob@example.com", row.text)
        self.assertNotIn("outside.example.net", row.text)
        self.assertEqual(row.links, ())

    def test_folded_property(self):
        row = extract_calendar(
            "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Flight\n"
            "DESCRIPTION:Climb and\n angle analysis\nEND:VEVENT\nEND:VCALENDAR",
        )
        self.assertIn("Climb andangle analysis", row.text)

    def test_recurrence_not_expanded(self):
        row = extract_calendar(
            "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Flight\n"
            "RRULE:FREQ=DAILY;COUNT=10000\nEND:VEVENT\nEND:VCALENDAR",
        )
        self.assertIn("not expanded", row.text)
        self.assertNotIn("10000", row.text)

    def test_alarm_mismatch_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_calendar("BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Flight\n"
                             "END:VALARM\nEND:VEVENT\nEND:VCALENDAR")

    def test_property_bomb_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_calendar("BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:" + "X"*8200
                             + "\nEND:VEVENT\nEND:VCALENDAR")

    def test_empty_calendar_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_calendar("BEGIN:VCALENDAR\nEND:VCALENDAR")


class BibliographyTests(unittest.TestCase):
    def test_ris_title_author_abstract_and_doi(self):
        row = extract_ris(RIS)
        self.assertIn("Stability of archived flight models", row.text)
        self.assertIn("Wing force and lift dynamics", row.text)
        self.assertIn("doi: 10.1234/original", row.text)
        self.assertNotIn("outside.example.net", row.text)
        self.assertEqual(row.links, ())

    def test_ris_nested_record_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_ris("TY  - JOUR\nTY  - BOOK\nTI  - Bad\nER  -")

    def test_ris_incomplete_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_ris("TY  - JOUR\nTI  - Missing ending")

    def test_bibtex_nested_braces(self):
        row = extract_bibtex("@article{a,title={{Lift} and {drag} research},year={2026}}")
        self.assertIn("{Lift} and {drag}", row.text)
        self.assertEqual(row.links, ())

    def test_bibtex_macros_denied(self):
        for source in ("@string{key={value}}", "@article{a,title=macro_name}"):
            with self.subTest(source=source), self.assertRaises(ResearchFormatError):
                extract_bibtex(source)

    def test_bibtex_duplicate_field_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_bibtex("@article{a,title={one},title={two}}")

    def test_bibtex_url_has_no_discovery_authority(self):
        row = extract_bibtex(
            "@article{a,title={https://outside.example.net/private}}",
        )
        self.assertEqual(row.links, ())


class NotebookTests(unittest.TestCase):
    def test_code_inert_outputs_metadata_and_secrets_discarded(self):
        row = extract_notebook(NOTEBOOK)
        self.assertIn("Wing performance", row.text)
        self.assertIn("angle_of_attack", row.text)
        self.assertNotIn("SECRET_OUTPUT", row.text)
        self.assertNotIn("SECRET_NONEXPORTED_METADATA", row.text)
        self.assertNotIn("SECRET_CODE_VALUE", row.text)
        self.assertIn("withheld", row.text)
        self.assertEqual(row.links, ())
        self.assertFalse(row.body_executed)

    def test_duplicate_keys_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_notebook('{"nbformat":4,"cells":[],"cells":[]}')

    def test_wrong_notebook_version_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_notebook('{"nbformat":3,"cells":[]}')

    def test_nonfinite_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_notebook('{"nbformat":4,"cells":[],"metadata":{"a":NaN}}')

    def test_unbounded_notebook_cell_denied(self):
        value = json.dumps({"nbformat":4, "cells":[{"cell_type":"code",
                                                   "source":"x"*65537}]})
        with self.assertRaises(ResearchFormatError):
            extract_notebook(value)


class RDFTests(unittest.TestCase):
    def test_ntriples_no_url_discovery(self):
        row = extract_rdf_lines(TRIPLES, "application/n-triples")
        self.assertIn("Original flight simulation", row.text)
        self.assertEqual(row.links, ())

    def test_nquads_has_graph(self):
        row = extract_rdf_lines(QUADS, "application/n-quads")
        self.assertIn("example.com/g", row.text)
        self.assertEqual(row.links, ())

    def test_malformed_statements_denied(self):
        for value in ("<https://example.com/s> nonsense .",
                      '<https://example.com/s> <https://example.com/p> "bad .'):
            with self.subTest(value=value), self.assertRaises(ResearchFormatError):
                extract_rdf_lines(value, "application/n-triples")

    def test_capacity_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_rdf_lines(TRIPLES*513, "application/n-triples")

    def test_control_bytes_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_rdf_lines(TRIPLES+"\x00", "application/n-triples")


class DispatchTests(unittest.TestCase):
    def test_mime_allowlist_is_explicit(self):
        for mime in ("text/vtt", "application/x-subrip", "text/calendar",
                     "application/x-research-info-systems", "application/x-bibtex",
                     "application/x-ipynb+json", "application/n-triples"):
            self.assertIn(mime, RESEARCH_ARTIFACT_TYPES)

    def test_unrecognized_mime_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_research_artifact(
                "external", "application/octet-stream",
                max_chars=1024, max_links=0,
            )


if __name__ == "__main__":
    unittest.main()
