"""No-extraction TAR catalog; reject symlinks and path traversal."""
from __future__ import annotations
import io
import tarfile
import unittest
from skeleton.ai.webcrawler.tar_inventory import extract_tar
from skeleton.ai.webcrawler.research_projection import ResearchFormatError


def tar(name="models/aircraft.obj",mode="file"):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode="w",format=tarfile.USTAR_FORMAT) as package:
        entry=tarfile.TarInfo(name)
        entry.size=4
        if mode=="symlink":
            entry.type=tarfile.SYMTYPE
            entry.linkname="../../private"
            entry.size=0
        package.addfile(entry,io.BytesIO(b"data") if mode=="file" else None)
    return out.getvalue()


class TARTests(unittest.TestCase):
    def test_archive_inventory_without_extraction(self):
        row=extract_tar(tar())
        self.assertIn("Extension class .obj: 1",row.text)
        self.assertNotIn("models/aircraft.obj",row.text)
        self.assertEqual(row.links,())

    def test_archive_path_traversal_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_tar(tar("../secret.txt"))

    def test_symlink_refused(self):
        with self.assertRaises(ResearchFormatError):
            extract_tar(tar("outside",mode="symlink"))

    def test_bad_header_checksum_rejected(self):
        body=bytearray(tar())
        body[0]=ord("Q")
        with self.assertRaises(ResearchFormatError):
            extract_tar(bytes(body))


if __name__=="__main__":
    unittest.main()
