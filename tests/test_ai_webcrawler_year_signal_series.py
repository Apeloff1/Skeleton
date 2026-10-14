from skeleton.ai.webcrawler.year_signals import YearSignalSeries
def test_year_signal_deltas_preserve_gaps_and_direction():
 s=YearSignalSeries({2022:{"distinct_hosts":1,"observations":2,"mean_relevance":.4,"mean_source_score":.5,"positive":2,"negative":0},2024:{"distinct_hosts":3,"observations":4,"mean_relevance":.6,"mean_source_score":.7,"positive":2,"negative":2}})
 d=s.deltas()
 assert d[1].year==2024 and d[1].previous_year==2022
 assert d[1].host_delta==2 and d[1].observation_delta==2 and d[1].polarity_delta==-2
def test_strongest_years_rank_diversity_before_volume():
 s=YearSignalSeries({2020:{"distinct_hosts":1,"observations":10},2021:{"distinct_hosts":2,"observations":2}})
 assert s.strongest_years()==(2021,2020)
