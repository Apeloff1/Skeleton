"""Studio episode budget consistency across project authority and engine actors."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from core.game_learning import GameLearningWorkspace
from skeleton.jeeves.game_studio_environment import make_studio_source, studio_request_tree
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest


class StudioEpisodeBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_play_and_campaign_source_share_bounded_episode_length(self):
        source=studio_request_tree(make_studio_source("economy"))
        project={"console_id":"studio:economy","project_id":"p","version":1,
                 "files":[{"path":path,"content":content} for path,content in source.items()],
                 "source_ids":[],"default_source_id":None,"derived_sources":[],
                 "derived_demonstrations":[]}
        workspace=GameLearningWorkspace.__new__(GameLearningWorkspace)
        workspace._editor_pending=lambda _:False
        workspace._authority=AsyncMock(return_value=project)
        workspace.sources=type("EmptySources",(),{
            "find":lambda self,query:self,
            "limit":lambda self,count:self,
            "to_list":AsyncMock(return_value=[]),
        })()
        binding=await workspace._input({},project,episode_steps=4096)
        self.assertEqual(binding["episode_steps"],128)
        request=GameEnvironmentRequest.from_dict(
            await workspace.environment_request({},binding)
        )
        self.assertEqual(request.kind,"studio")
        self.assertEqual(request.max_steps,128)
        env=request.build()
        env.reset(17)
        self.assertEqual(env.spec.max_episode_steps,128)
        env.close()


if __name__=="__main__":
    unittest.main()
