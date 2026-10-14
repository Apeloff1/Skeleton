from skeleton.ai.webcrawler.recrawl import RecrawlScheduler

def test_stable_source_backs_off_and_changed_source_tightens():
 s=RecrawlScheduler(min_interval=100,max_interval=10000)
 first=s.observe("https://a.example/",now=0,changed=False,source_score=.5)
 second=s.observe("https://a.example/",now=10,changed=False,source_score=.5)
 assert second.interval >= first.interval
 third=s.observe("https://a.example/",now=20,changed=True,source_score=.5)
 assert third.interval < second.interval

def test_only_latest_schedule_for_url_is_emitted():
 s=RecrawlScheduler(min_interval=10,max_interval=100)
 old=s.observe("https://a.example/",now=0,changed=False)
 new=s.observe("https://a.example/",now=1,changed=True)
 due=s.due(now=1000)
 assert len(due)==1 and due[0] is new

def test_higher_value_source_is_revisited_sooner():
 a=RecrawlScheduler(min_interval=10,max_interval=1000)
 low=a.observe("https://low.example/",now=0,changed=False,source_score=.1)
 high=a.observe("https://high.example/",now=0,changed=False,source_score=1)
 assert high.interval < low.interval
