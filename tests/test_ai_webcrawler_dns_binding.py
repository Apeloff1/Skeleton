from skeleton.ai.webcrawler.dns_binding import ResolvedTarget,peer_is_planned
def test_peer_must_match_prevalidated_resolution_set():
 t=ResolvedTarget("https://example.org/","example.org",443,("93.184.216.34","93.184.216.35"))
 assert peer_is_planned("93.184.216.34",t)
 assert not peer_is_planned("127.0.0.1",t)
 assert not peer_is_planned("10.0.0.1",t)
def test_invalid_peer_text_fails_closed():
 t=ResolvedTarget("https://example.org/","example.org",443,("93.184.216.34",))
 assert not peer_is_planned("not-an-ip",t)
