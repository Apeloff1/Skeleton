from skeleton.ai.webcrawler.mime import MimeExtractor
def test_declared_latin1_is_decoded_strictly():
 x=MimeExtractor().extract("café".encode("latin-1"),"text/plain; charset=iso-8859-1")
 assert x and x.text=="café" and x.charset=="iso-8859-1"
def test_unknown_charset_fails_closed():
 assert MimeExtractor().extract(b"abc","text/plain; charset=x-unsafe") is None
def test_byte_limit_applies_before_decode():
 assert MimeExtractor(max_bytes=3).extract(b"abcd","text/plain") is None
def test_malformed_utf8_fails_closed():
 assert MimeExtractor().extract(b"\xff","text/plain; charset=utf-8") is None
