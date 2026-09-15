"""Tests for the ResponseCycle and its Jeeves integration."""

from __future__ import annotations

import unittest


class TestConnectorExecutor(unittest.TestCase):
    def test_simulated_execution_offline(self):
        from skeleton.contexts import ConnectorExecutor, WorkOrder
        ex = ConnectorExecutor()
        order = WorkOrder(order_id="sim-1", connector="github.push", action="push",
                          payload={"context": "push the batch"})
        outcome = ex.execute(order)
        self.assertTrue(outcome["ok"])
        self.assertTrue(outcome["result"]["simulated"])

    def test_registered_handler_runs(self):
        from skeleton.contexts import ConnectorExecutor, WorkOrder
        ex = ConnectorExecutor()
        ex.register("web.search", lambda o: {"hits": 3, "query": o.payload.get("context")})
        order = WorkOrder(order_id="h-1", connector="web.search", action="search the web",
                          payload={"context": "find docs"})
        outcome = ex.execute(order)
        self.assertEqual(outcome["result"]["hits"], 3)
        self.assertEqual(ex.stats()["executed"], 1)

    def test_handler_failure_returns_not_ok(self):
        from skeleton.contexts import ConnectorExecutor, WorkOrder
        ex = ConnectorExecutor()
        def boom(o):
            raise RuntimeError("connector down")
        ex.register("github.push", boom)
        order = WorkOrder(order_id="f-1", connector="github.push", action="push", payload={})
        outcome = ex.execute(order)
        self.assertFalse(outcome["ok"])
        self.assertIn("connector down", outcome["error"])


class TestResponseCycle(unittest.TestCase):
    def _cycle(self):
        from skeleton.contexts import ContextFabric, ResponseCycle
        fabric = ContextFabric()
        fabric.connect_all()
        return fabric, ResponseCycle(fabric)

    def test_after_reply_parses_and_executes(self):
        fabric, cycle = self._cycle()
        report = cycle.after_reply(
            "Plan set. Push these files to github. Then search the web for docs. Build pdf of the report.",
            token_count=2000,
        )
        self.assertGreaterEqual(report.orders_parsed, 1)
        self.assertGreaterEqual(report.orders_executed, 1)
        self.assertEqual(fabric.workorders.stats()["completed"], report.orders_executed)

    def test_failed_execution_defers_to_backlog(self):
        from skeleton.contexts import ContextFabric, ResponseCycle
        fabric = ContextFabric()
        fabric.connect_all()
        cycle = ResponseCycle(fabric)
        def boom(o):
            raise RuntimeError("down")
        cycle.executor.register("github.push", boom)
        report = cycle.after_reply("push the files", 100)
        self.assertEqual(report.orders_failed, 1)
        self.assertGreater(len(fabric.backlog.items), 0)

    def test_interjection_flows_to_next_reply(self):
        fabric, cycle = self._cycle()
        cycle.after_reply("push the batch", 500)
        interjection = cycle.before_reply()
        self.assertIsNotNone(interjection)
        self.assertIn("landed", interjection)
        # Consumed once
        self.assertIsNone(cycle.before_reply())

    def test_bounded_executions_per_turn(self):
        fabric, cycle = self._cycle()
        cycle.max_executions = 1
        cycle.after_reply("push a. push b. push c. search the web for x. build pdf.", 800)
        done = fabric.workorders.stats()["completed"]
        self.assertLessEqual(done, 1)

    def test_cycle_stats_shape(self):
        fabric, cycle = self._cycle()
        cycle.after_reply("push files", 100)
        stats = cycle.stats()
        self.assertIn("turns", stats)
        self.assertIn("executor", stats)


class TestJeevesCycleIntegration(unittest.TestCase):
    def test_ask_runs_cycle_between_turns(self):
        from skeleton.contexts import ContextFabric, ResponseCycle
        from skeleton.jeeves import JeevesCore
        from skeleton.jeeves.providers import LocalEchoProvider

        fabric = ContextFabric()
        fabric.connect_all()
        cycle = ResponseCycle(fabric)
        jeeves = JeevesCore(provider=LocalEchoProvider(), cycle=cycle)

        session = jeeves.open_session("cycle-user")
        r1 = jeeves.ask(session.session_id, "push these files to github")
        self.assertIn("cycle", r1)
        self.assertGreaterEqual(r1["cycle"]["orders_parsed"], 1)

    def test_second_turn_carries_interjection(self):
        from skeleton.contexts import ContextFabric, ResponseCycle
        from skeleton.jeeves import JeevesCore
        from skeleton.jeeves.providers import LocalEchoProvider

        fabric = ContextFabric()
        fabric.connect_all()
        cycle = ResponseCycle(fabric)
        jeeves = JeevesCore(provider=LocalEchoProvider(), cycle=cycle)

        session = jeeves.open_session("interject-user")
        jeeves.ask(session.session_id, "push the files")
        r2 = jeeves.ask(session.session_id, "anything else?")
        self.assertIn("interjection", r2)
        self.assertIn("landed", r2["content"])

    def test_server_state_passes_genesis_cycle(self):
        from skeleton.api.server import ServerState
        from skeleton.genesis import Genesis

        state = ServerState()
        state.wire_from_genesis(Genesis(seed=42).boot())
        self.assertIsNotNone(state.jeeves._cycle)

        session = state.jeeves.open_session("wired-user")
        reply = state.jeeves.ask(session.session_id, "push files and search the web for docs")
        self.assertIn("cycle", reply)

    def test_genesis_wires_cycle_handle(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        self.assertIn("cycle", g.handles)
        self.assertIs(g.get("cycle")._fabric, g.get("fabric"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
