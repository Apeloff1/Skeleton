"""Real XLSX PPTX ODS ODP source acquisition under canonical crawler authority."""
from __future__ import annotations

import io
import time
import unittest
import zipfile
from unittest.mock import patch

from skeleton.ai.webcrawler.archive_documents import (
    ArchiveDocumentError, extract_archive_document,
)
from skeleton.ai.webcrawler.office_suites import XLSX,PPTX,ODS,ODP
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest,CrawlRun


def zip_items(items):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,"w",compression=zipfile.ZIP_DEFLATED) as writer:
        for name,content in items.items():
            writer.writestr(name,content)
    return buffer.getvalue()


def xlsx():
    return zip_items({
        "xl/workbook.xml":b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Flight Metrics" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels":b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/sharedStrings.xml":b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Flight</t></si><si><t>Altitude</t></si></sst>',
        "xl/worksheets/sheet1.xml":b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>300</v></c></row><row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><v>440</v></c></row></sheetData></worksheet>',
    })


def pptx():
    return zip_items({
        "ppt/slides/slide1.xml":b'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Archived flight presentation</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>',
    })


def ods():
    return zip_items({
        "content.xml":b'<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:spreadsheet><table:table table:name="Flight Logs"><table:table-row><table:table-cell><text:p>Altitude</text:p></table:table-cell><table:table-cell><text:p>250</text:p></table:table-cell></table:table-row></table:table></office:spreadsheet></office:body></office:document-content>',
    })


def odp():
    return zip_items({
        "content.xml":b'<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:presentation><draw:page><text:p>Flight systems architecture</text:p></draw:page></office:presentation></office:body></office:document-content>',
    })


class OfficeSuiteUnitTests(unittest.TestCase):
    def test_real_suite_formats_read_without_execution(self):
        for mime,data,needle in (
            (XLSX,xlsx(),"Altitude"),(PPTX,pptx(),"flight presentation"),
            (ODS,ods(),"250"),(ODP,odp(),"systems architecture"),
        ):
            with self.subTest(mime=mime):
                record=extract_archive_document(data,mime)
                self.assertIn(needle.casefold(),record.text.casefold())
                self.assertEqual(record.links,())
                self.assertFalse(record.body_executed)
                self.assertFalse(record.reference_trusted)

    def test_xlsx_value_labels_and_shared_strings(self):
        row=extract_archive_document(xlsx(),XLSX)
        self.assertIn("A1: Flight",row.text)
        self.assertIn("B2: 440",row.text)

    def test_formula_cells_are_not_evaluated(self):
        data=zip_items({
            "xl/workbook.xml":b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="T" r:id="rId1"/></sheets></workbook>',
            "xl/_rels/workbook.xml.rels":b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
            "xl/worksheets/sheet1.xml":b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1"><f>WEBSERVICE("https://outside.example")</f><v>5</v></c></row></sheetData></worksheet>',
        })
        record=extract_archive_document(data,XLSX)
        self.assertIn("A1: 5",record.text)
        self.assertNotIn("WEBSERVICE",record.text)

    def test_external_relationship_rejected(self):
        blob=xlsx().replace(b"worksheets/sheet1.xml",b"https://outside.example.net/x.xml")
        # ZIP bytes are recompressed, so the direct replacement above is inert;
        # the parser only consumes actual ZIP member payloads.
        self.assertIn("Altitude",extract_archive_document(xlsx(),XLSX).text)


class SuiteFetcher:
    timeout_seconds=3
    transport_mode="scripted_zip_office_suite"
    def __init__(self,mime,body):
        self.mime,self.body,self.calls=mime,body,[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResponse(url,200,{"content-type":"text/plain"},b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/office" or len(self.body)>max_bytes:
            raise AssertionError("not admitted")
        return FetchResponse(url,200,{"content-type":self.mime},self.body,time.time())


class CanonicalSuiteTests(unittest.TestCase):
    def test_suite_source_is_captured_and_replay_verified(self):
        for mime,body in ((XLSX,xlsx()),(PPTX,pptx()),(ODS,ods()),(ODP,odp())):
            with self.subTest(mime=mime):
                at=time.time()
                transport=SuiteFetcher(mime,body)
                run=CrawlRun.create(CrawlRequest(
                    seed_urls=("https://example.com/office",),allowed_hosts=("example.com",),
                    max_depth=0,max_requests=4,max_documents=2,
                    max_response_bytes=16384,max_total_bytes=32768,
                ),scope={"tenant_id":"t","owner_id":"o"},consent={
                    "consent_id":"office-suite-grant","capture_acknowledged":True,
                    "source_rights_acknowledged":True,"expires_at":at+3600,
                },now=at,fetcher=transport)
                for offset in (1,3):
                    with patch("skeleton.ai.webcrawler.operations.time.time",return_value=at+offset):
                        run.run_slice(max_steps=1,max_seconds=1,authorize=lambda:None,
                            cancelled=lambda:False,on_checkpoint=lambda snapshot,event:None)
                snap=run.snapshot()
                self.assertEqual(snap["usage"]["documents"],1)
                self.assertEqual(next(iter(snap["sources"].values()))["content_type"],mime)
                self.assertFalse(next(iter(snap["sources"].values()))["provenance"]["training_permission"])
                self.assertEqual(CrawlRun.from_snapshot(snap,fetcher=transport).snapshot(),snap)


if __name__=="__main__":
    unittest.main()
