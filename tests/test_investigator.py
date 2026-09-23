"""No live calls, environment reads, or secret loading in investigator tests."""

from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import networkx as nx
from pydantic import ValidationError

from backend import investigator as agent
from backend.models import InvestigateRequest


A, B, C = "100000008603629100", "100000000331309100", "100000000437046100"


def analysis():
    graph = nx.DiGraph()
    graph.add_edge(A, B, weight=100.0, count=1)
    graph.add_edge(A, C, weight=20.0, count=1)
    nodes = {}
    for node in graph:
        nodes[node] = {"node_id": node, "priority_score": 82.0 if node == A else 70.0,
                       "role": "distributor" if node == A else "peripheral", "role_evidence": "Численная эвристика.",
                       "is_seed": node == A, "depth": 0 if node == A else 1, "truncated_by_depth": False,
                       "features": {"incoming_counterparties": graph.in_degree(node), "outgoing_counterparties": graph.out_degree(node)}}
    edges = [
        {"id": "tx-1", "source": A, "target": B, "amount": 100.0, "timestamp": "2026-07-01T00:00:00+00:00"},
        {"id": "tx-2", "source": A, "target": C, "amount": 20.0, "timestamp": "2026-07-02T00:00:00+00:00"},
    ]
    return SimpleNamespace(graph=graph, nodes=nodes, edges=edges, metadata={"time_precision": "day", "currency": "KZT"})


def tool(name, node=A, call_id="call-1", **kwargs):
    return SimpleNamespace(type="function_call", name=name, call_id=call_id,
                           arguments=json.dumps({"node_id": node, **kwargs}))


def call_response(call):
    return SimpleNamespace(output=[call], output_text="")


def final_response(ids, next_node=None, checks=None, **extra):
    return SimpleNamespace(output=[], output_text=json.dumps({"finding_ids": ids,
                           "next_node_id": next_node, "check_codes": checks or ["missing_data"], **extra}))


class FakeClient:
    def __init__(self, responses):
        self.responses = self
        self.script = list(responses)
        self.calls = []
        self.closed = False

    def create(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        if not self.script:
            raise RuntimeError("Mock script exhausted; no network is available.")
        response = self.script.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        self.closed = True


class InvestigatorTests(unittest.TestCase):
    def run_mock(self, script, dataset=None):
        client = FakeClient(script)
        with patch.object(agent.os, "getenv", side_effect=lambda name, default="": "test-only" if name == "OPENAI_API_KEY" else default), \
             patch.object(agent, "OpenAI", return_value=client) as constructor:
            result = agent.investigate(dataset or analysis(), A, "Куда проверить дальше?")
        return result, client, constructor

    def test_model_chooses_multiple_tools_using_previous_results_and_cannot_mutate(self):
        dataset = analysis()
        before = deepcopy((dataset.nodes, dataset.edges, list(dataset.graph.edges(data=True))))
        # fact-1: A; fact-2: seed limit; fact-3/4: A→B/C; fact-5: B; fact-6/7: transactions.
        result, client, constructor = self.run_mock([
            call_response(tool("get_account", call_id="a")),
            call_response(tool("get_connections", call_id="b", direction="outgoing")),
            call_response(tool("get_account", B, call_id="c")),
            call_response(tool("get_transactions", call_id="d")),
            final_response(["fact-1", "fact-3", "fact-6"], B),
        ], dataset)
        self.assertEqual((result["mode"], result["status"]), ("agent", "completed"))
        self.assertEqual(result["next_node_id"], B)
        self.assertEqual(len(result["trace"]), 4)
        self.assertTrue(all(item["status"] == "ok" for item in result["trace"]))
        self.assertEqual(result["findings"][-1]["transaction_ids"], ["tx-1"])
        self.assertNotIn("T00:00", result["findings"][-1]["text"])
        self.assertIn(B, result["evidence_node_ids"])
        self.assertEqual(before, (dataset.nodes, dataset.edges, list(dataset.graph.edges(data=True))))
        self.assertTrue(client.closed)
        self.assertEqual(constructor.call_args.kwargs["max_retries"], 0)
        second_input = client.calls[1]["input"]
        self.assertTrue(any(isinstance(item, dict) and item.get("type") == "function_call_output" for item in second_input))
        for request in client.calls:
            self.assertFalse(request["store"])
            self.assertLessEqual(request["timeout"], 15)
            self.assertEqual(len(request["tools"]), 3)
            self.assertNotIn("test-only", json.dumps(request["input"], default=lambda obj: vars(obj)))

    def test_final_turn_forces_decision_without_executing_another_tool(self):
        result, client, _ = self.run_mock([call_response(tool("get_account", call_id=str(i))) for i in range(20)])
        self.assertEqual(result["status"], "limited")
        self.assertEqual(len(result["trace"]), agent.MAX_MODEL_TURNS - 1)
        self.assertEqual(len(client.calls), agent.MAX_MODEL_TURNS)
        self.assertIsNone(result["next_node_id"])
        self.assertEqual(client.calls[-1]["tool_choice"], "none")
        self.assertIn("последний доступный ход", client.calls[-1]["instructions"])
        self.assertIn("финальном ходе", result["notice"])
        self.assertEqual(sum(item["status"] == "ok" for item in result["trace"]), 1)

    def test_identical_successful_request_is_not_reexecuted(self):
        state = agent._Investigation(analysis(), A)
        state.execute(tool("get_account", call_id="one"))
        initial_fact_count = len(state.facts)
        output = state.execute(tool("get_account", call_id="two"))
        self.assertIn("уже выполнен", output["error"])
        self.assertEqual(state.trace[-1]["status"], "rejected")
        self.assertEqual(len(state.facts), initial_fact_count)

    def test_five_attempt_limit_stops_excess_model_calls_in_same_response(self):
        # Defend the limit even if a provider ignores parallel_tool_calls=False.
        response = SimpleNamespace(output=[tool("get_account", call_id=str(i)) for i in range(7)], output_text="")
        result, client, _ = self.run_mock([response])
        self.assertEqual(result["status"], "limited")
        self.assertEqual(len(result["trace"]), agent.MAX_TOOL_CALLS)
        self.assertEqual(len(client.calls), 1)

    def test_final_validation_failure_is_explained_without_model_text(self):
        result, _, _ = self.run_mock([
            call_response(tool("get_account", call_id="a")),
            call_response(tool("get_connections", call_id="b", direction="both")),
            final_response(["FORGED-FACT"]),
            final_response(["FORGED-FACT"]),
            final_response(["FORGED-FACT"]),
        ])
        self.assertEqual(result["status"], "limited")
        self.assertIn("fact_id", result["notice"])
        self.assertNotIn("FORGED-FACT", json.dumps(result))

    def test_unknown_tool_is_rejected_then_model_can_recover(self):
        result, _, _ = self.run_mock([
            call_response(tool("delete_account", call_id="bad")),
            call_response(tool("get_account", call_id="a")),
            call_response(tool("get_connections", call_id="b", direction="both")),
            final_response(["fact-1"]),
        ])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["trace"][0]["status"], "rejected")
        self.assertEqual(result["trace"][0]["tool"], "unknown")

    def test_arguments_reject_unknown_unobserved_ids_and_extra_fields(self):
        state = agent._Investigation(analysis(), A)
        calls = [tool("get_account", B, "a"), tool("get_account", "NONEXISTENT", "b"),
                 tool("get_account", A, "c", ignore_limits=True),
                 tool("get_connections", A, "d", direction="sideways")]
        for call in calls:
            self.assertIn("error", state.execute(call))
        self.assertEqual(state.facts, {})
        self.assertTrue(all(step["status"] == "rejected" for step in state.trace))

    def test_malformed_or_duplicate_calls_do_not_execute(self):
        state = agent._Investigation(analysis(), A)
        call = tool("get_account", call_id="a")
        state.execute(call)
        self.assertIn("error", state.execute(call))
        malformed = tool("get_account", call_id="b")
        malformed.arguments = "not JSON"
        self.assertIn("error", state.execute(malformed))
        self.assertEqual(len(state.accounts_checked), 1)

    def test_forged_final_fact_ids_are_rejected_not_displayed(self):
        result, _, _ = self.run_mock([
            call_response(tool("get_account", call_id="a")),
            call_response(tool("get_connections", call_id="b", direction="both")),
            final_response(["INVENTED_TRANSACTION"]),
            final_response(["fact-1"]),
        ])
        self.assertEqual(result["status"], "completed")
        self.assertNotIn("INVENTED", json.dumps(result))

    def test_final_next_node_requires_its_actual_account_tool(self):
        state = agent._Investigation(analysis(), A)
        state.execute(tool("get_account", call_id="a"))
        state.execute(tool("get_connections", call_id="b", direction="both"))
        with self.assertRaises(ValueError):
            state.decision(final_response(["fact-1"], B).output_text)
        state.execute(tool("get_account", B, "c"))
        self.assertEqual(state.decision(final_response(["fact-1"], B).output_text)[1], B)

    def test_free_form_facts_are_not_accepted_from_model(self):
        state = agent._Investigation(analysis(), A)
        state.execute(tool("get_account", call_id="a"))
        state.execute(tool("get_connections", call_id="b", direction="both"))
        with self.assertRaises(ValueError):
            state.decision(final_response(["fact-1"], summary="Invented 999999").output_text)

    def test_no_key_means_no_agent_steps_or_network(self):
        with patch.object(agent.os, "getenv", return_value=""), patch.object(agent, "OpenAI") as constructor:
            result = agent.investigate(analysis(), A)
        constructor.assert_not_called()
        self.assertEqual((result["mode"], result["status"]), ("rules", "unavailable"))
        self.assertEqual(result["trace"], [])
        self.assertEqual(result["findings"], [])

    def test_api_error_is_not_exposed(self):
        result, _, _ = self.run_mock([RuntimeError("PRIVATE-ERROR-CONTENT")])
        self.assertEqual(result["mode"], "rules")
        self.assertEqual(result["trace"], [])
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_deadline_stops_before_executing_late_tool(self):
        with patch.object(agent.time, "monotonic", side_effect=[0, 0, 46]):
            result, client, _ = self.run_mock([call_response(tool("get_account"))])
        self.assertEqual(result["status"], "limited")
        self.assertEqual(result["trace"], [])
        self.assertEqual(len(client.calls), 1)

    def test_output_sampling_is_bounded(self):
        dataset = analysis()
        for index in range(20):
            node = f"N-{index}"
            dataset.graph.add_edge(A, node, weight=index + 1.0, count=1)
            dataset.nodes[node] = deepcopy(dataset.nodes[B])
            dataset.nodes[node]["node_id"] = node
            dataset.edges.append({"id": f"extra-{index}", "source": A, "target": node,
                                  "amount": index + 1.0, "timestamp": "2026-07-01T00:00:00+00:00"})
        state = agent._Investigation(dataset, A)
        output = state.execute(tool("get_connections", call_id="c", direction="both"))
        self.assertEqual(output["shown"], agent.MAX_CONNECTIONS)
        self.assertTrue(output["truncated"])
        output = state.execute(tool("get_transactions", call_id="t"))
        self.assertEqual(len(output["transactions"]), agent.MAX_TRANSACTIONS)
        self.assertTrue(output["truncated"])

    def test_request_bounds_keep_ids_as_strings(self):
        self.assertEqual(InvestigateRequest(node_id=A).node_id, A)
        with self.assertRaises(ValidationError):
            InvestigateRequest(node_id=A, question="x" * 1001)

    def test_api_route_validation_and_mock_contract(self):
        # Import without loading a developer's .env, even when run standalone.
        with patch("dotenv.load_dotenv", return_value=False):
            from backend.main import app, analyzed
        from fastapi.testclient import TestClient
        dataset = analysis()
        previous = dict(app.dependency_overrides)
        app.dependency_overrides[analyzed] = lambda: dataset
        expected = agent._Investigation(dataset, A).result("agent", "limited", "Mock only")
        try:
            with patch.object(agent, "investigate", return_value=expected) as mocked:
                client = TestClient(app)
                response = client.post("/api/ai/investigate", json={"node_id": A, "question": "Проверить связи"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), expected)
                mocked.assert_called_once_with(dataset, A, "Проверить связи")
                self.assertEqual(client.post("/api/ai/investigate", json={"node_id": "missing"}).status_code, 404)
                self.assertEqual(client.post("/api/ai/investigate", json={"node_id": A, "question": "x" * 1001}).status_code, 422)
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    def test_api_without_key_reports_no_fabricated_agent_steps(self):
        with patch("dotenv.load_dotenv", return_value=False):
            from backend.main import app, analyzed
        from fastapi.testclient import TestClient
        previous = dict(app.dependency_overrides)
        app.dependency_overrides[analyzed] = analysis
        try:
            with patch.object(agent.os, "getenv", side_effect=lambda name, default="": "" if name == "OPENAI_API_KEY" else default), \
                 patch.object(agent, "OpenAI") as constructor:
                response = TestClient(app).post("/api/ai/investigate", json={"node_id": A})
            constructor.assert_not_called()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["mode"], "rules")
            self.assertEqual(response.json()["status"], "unavailable")
            self.assertEqual(response.json()["trace"], [])
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)


if __name__ == "__main__":
    unittest.main()
