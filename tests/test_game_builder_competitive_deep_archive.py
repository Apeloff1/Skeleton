"""Tamper-aware evolving enemy dossiers and revisable game almanac persistence."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.competitive_deep_archive import DeepEnemyArchive
from skeleton.ai.game_builder.competitive_deep_service import examine_enemy_genre_portfolio
from skeleton.ai.game_builder.competitive_watch_service import review_competitive_frontier
from skeleton.ai.game_builder.competitive_watch_book import CompetitionWatchBook
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.competitive_title_radar import ThreatRadarError
from tests.test_game_builder_competitive_deep import DeepEnemyCases,T0,T1


class DeepHistoryCases(DeepEnemyCases):
    def scan(self,watch,*,at):
        return review_competitive_frontier(
            watch,self.original,(self.competitor,),tuple(self.links),
            self.brief,self.packet,self.db,self.rights,as_of=at,
            authorized=True)

    def dossier(self,overview):
        return examine_enemy_genre_portfolio(
            overview,self.original,(self.competitor,),
            self.titles,self.edges,tuple(self.deep_links),
            self.deep_brief,self.deep_packet,self.deep_db,self.deep_rights,
            platform="pc",judges=self.judges,authorized=True)

    def test_repeated_enemy_deep_dossiers_make_immutable_evolution_chain(self):
        with TemporaryDirectory() as d:
            root=Path(d)/"games"
            GameWorkspace.create(root,authorized=True)
            with CompetitionWatchBook(root) as watch,DeepEnemyArchive(root) as archive:
                current=self.scan(watch,at=T0)
                dossier=self.dossier(current)
                first=archive.record(
                    dossier,current,self.deep_brief,self.deep_packet,
                    self.deep_db,self.deep_rights,
                    as_of=T0,expected_parent_digest=None,authorized=True)
                self.assertEqual(first.revision,0)
                self.assertEqual(first.enemy_ids,("other_atlas",))
                self.assertEqual(len(dossier.enemy_dossiers[0].analysis_scripts),51)
                with self.assertRaises(ThreatRadarError):
                    archive.record(
                        dossier,current,self.deep_brief,self.deep_packet,
                        self.deep_db,self.deep_rights,as_of=T0,
                        expected_parent_digest=None,authorized=True)
                next_scan=self.scan(watch,at=T1)
                second_dossier=self.dossier(next_scan)
                second=archive.record(
                    second_dossier,next_scan,self.deep_brief,self.deep_packet,
                    self.deep_db,self.deep_rights,as_of=T1,
                    expected_parent_digest=first.entry_digest,authorized=True)
                self.assertEqual(second.parent_digest,first.entry_digest)
                self.assertEqual(second.revision,1)
                self.assertEqual(len(archive.history(
                    self.original.title_id,authorized=True)),2)
                with self.assertRaisesRegex(ThreatRadarError,"stale"):
                    archive.record(
                        second_dossier,next_scan,self.deep_brief,self.deep_packet,
                        self.deep_db,self.deep_rights,
                        as_of="2026-10-13T12:00:00Z",
                        expected_parent_digest="0"*64,authorized=True)
            with DeepEnemyArchive(root) as reopened:
                before=reopened.history(self.original.title_id,authorized=True)
                self.assertEqual(before[-1][1],second.entry_digest)
                reopened.db.execute(
                    "UPDATE competitor_deep_archive SET content_json=? "
                    "WHERE original_id=? AND revision=0",
                    ("{}",self.original.title_id))
                with self.assertRaisesRegex(ThreatRadarError,"integrity"):
                    reopened.history(self.original.title_id,authorized=True)

    def test_unscoped_rival_or_missing_facet_cannot_claim_persisted_dossier(self):
        with TemporaryDirectory() as d:
            root=Path(d)/"games"
            GameWorkspace.create(root,authorized=True)
            with CompetitionWatchBook(root) as watch,DeepEnemyArchive(root) as archive:
                current=self.scan(watch,at=T0)
                dossier=self.dossier(current)
                enemy=dossier.enemy_dossiers[0]
                incomplete=replace(enemy,analysis_scripts=enemy.analysis_scripts[:-1])
                inconsistent=replace(dossier,enemy_dossiers=(incomplete,))
                with self.assertRaises(ThreatRadarError):
                    archive.record(
                        inconsistent,current,self.deep_brief,self.deep_packet,
                        self.deep_db,self.deep_rights,
                        as_of=T0,expected_parent_digest=None,authorized=True)
                missing=replace(dossier,enemy_dossiers=())
                with self.assertRaises(ThreatRadarError):
                    archive.record(
                        missing,current,self.deep_brief,self.deep_packet,
                        self.deep_db,self.deep_rights,
                        as_of=T0,expected_parent_digest=None,authorized=True)
                with self.assertRaises(PermissionError):
                    archive.record(
                        dossier,current,self.deep_brief,self.deep_packet,
                        self.deep_db,self.deep_rights,
                        as_of=T0,expected_parent_digest=None,authorized=False)
                self.assertEqual(archive.history(
                    self.original.title_id,authorized=True),())


if __name__=="__main__":
    unittest.main()
