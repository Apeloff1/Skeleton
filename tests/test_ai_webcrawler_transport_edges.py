from skeleton.ai.webcrawler.bound_http import SocketBoundFetcher
def test_negative_response_limit_rejected_before_resolution():
 f=SocketBoundFetcher()
 try:f.fetch_once("https://example.org",user_agent="x",max_bytes=-1)
 except ValueError as exc:assert "max_bytes" in str(exc)
 else:raise AssertionError("negative byte limit accepted")
