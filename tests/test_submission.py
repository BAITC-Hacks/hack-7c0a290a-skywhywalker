import io
import json
from types import SimpleNamespace
import zipfile

import networkx as nx
import pandas as pd
import pytest

from backend.roles_engine import assign_roles
from backend.submission import frames_for_analysis, write_outputs, zip_for_analysis


def role_case(rows, metadata=None, between=None):
    df = pd.DataFrame(rows, columns=["sender", "receiver", "amount", "timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="mixed")
    df.attrs["node_metadata"] = metadata or {}
    graph = nx.DiGraph()
    graph.add_nodes_from(df.attrs["node_metadata"])
    for row in df.itertuples(index=False):
        graph.add_edge(row.sender, row.receiver)
    features = {}
    for gid in graph:
        incoming, outgoing = df[df.receiver == gid], df[df.sender == gid]
        features[gid] = {
            "incoming_counterparties": len(set(incoming.sender) - {gid}),
            "outgoing_counterparties": len(set(outgoing.receiver) - {gid}),
            "total_incoming_amount": float(incoming.amount.sum()),
            "total_outgoing_amount": float(outgoing.amount.sum()),
            "betweenness": (between or {}).get(gid, 0.0),
            "community_id": 1,
        }
    return assign_roles(features, graph, df)


def test_roles_protect_seeds_depth_boundary_unknown_depth_and_isolated_nodes():
    rows = [(payer, target, 100, "2026-07-01") for target in ("boundary", "hold", "unknown") for payer in ("P1", "P2", "P3")]
    rows += [("P1", "sink", 100, "2026-07-01"), ("P1", "seed", 100, "2026-07-01")]
    roles = role_case(rows, {
        "boundary": {"depth": 4, "is_seed": False},
        "hold": {"depth": 2, "is_seed": False},
        "sink": {"depth": 2, "is_seed": False},
        "seed": {"depth": 0, "is_seed": True},
        "isolated": {"depth": 4, "is_seed": False},
    })
    assert roles["boundary"]["role"] == "peripheral"
    assert roles["boundary"]["truncated_by_depth"] is True
    assert roles["hold"]["role"] == "consolidator"
    assert roles["hold"]["retention_ratio"] == 1
    assert roles["sink"]["role"] == "terminal"
    assert roles["unknown"]["role"] == "peripheral"
    assert roles["unknown"]["depth"] is None
    assert roles["seed"]["role"] == "peripheral"
    assert roles["seed"]["retention_ratio"] is None
    assert roles["isolated"]["role"] == "peripheral"
    assert roles["isolated"]["pass_through_ratio"] is None
    json.dumps(roles, ensure_ascii=False, allow_nan=False)
    assert all(0 <= node["role_score"] <= 1 and 1 <= len(node["role_evidence"]) <= 200 for node in roles.values())


def test_unknown_depth_fallback_evidence_reports_observed_numeric_counts():
    roles = role_case([("A", "sink", 100, "2026-07-01")], {"isolated": {}})
    assert roles["sink"]["role"] == roles["isolated"]["role"] == "peripheral"
    assert "плательщиков: 1, получателей: 0" in roles["sink"]["role_evidence"]
    assert "плательщиков: 0, получателей: 0" in roles["isolated"]["role_evidence"]
    for node in roles.values():
        assert 0 < len(node["role_evidence"]) <= 200
        assert any(character.isdigit() for character in node["role_evidence"])


def test_coordinator_distributor_and_transit_use_team_rules():
    rows = [("S1", "hub", 100, "2026-07-01"), ("S2", "hub", 100, "2026-07-01"),
            ("hub", "X", 100, "2026-07-02"), ("hub", "Y", 100, "2026-07-02"),
            ("A", "T", 100, "2026-07-01"), ("T", "B", 100, "2026-07-04")]
    rows += [("D", f"receiver-{i}", 10, "2026-07-01") for i in range(5)]
    roles = role_case(rows, {"S1": {"is_seed": True, "depth": 0}, "S2": {"is_seed": True, "depth": 0}}, {"hub": 0.9})
    assert roles["hub"]["role"] == "coordinator"
    assert roles["hub"]["seed_reach"] == 2
    assert roles["D"]["role"] == "distributor"
    assert roles["T"]["role"] == "transit"
    assert roles["T"]["fast_forward_fraction"] == 0


def test_seed_reach_is_directed_and_stops_at_four_hops():
    rows = [(str(i), str(i + 1), 10, "2026-07-01") for i in range(6)]
    rows += [("upstream", "0", 10, "2026-07-01")]
    roles = role_case(rows, {"0": {"is_seed": True, "depth": 0}})
    assert [roles[str(i)]["seed_reach"] for i in range(7)] == [1, 1, 1, 1, 1, 0, 0]
    assert roles["upstream"]["seed_reach"] == 0


def test_forward_signal_uses_calendar_days_not_minutes_or_self_transfers():
    rows = [
        ("A", "T", 100, "2026-07-01T23:59:00Z"),
        ("T", "B", 100, "2026-07-03T00:00:00Z"),
        ("A", "T", 100, "2026-07-04T00:00:00Z"),
        ("T", "T", 1000, "2026-07-05T00:00:00Z"),
        ("A", "U", 100, "2026-07-01T00:00:00Z"),
        ("U", "B", 100, "2026-07-04T00:00:00Z"),
        ("A", "V", 100, "2026-07-01T23:59:00Z"),
        ("V", "B", 100, "2026-07-01T00:00:00Z"),
    ]
    roles = role_case(rows)
    assert roles["T"]["fast_forward_fraction"] == 0.5
    assert roles["U"]["fast_forward_fraction"] == 0
    # A date-level coincidence intentionally makes no claim about intraday order.
    assert roles["V"]["fast_forward_fraction"] == 1
    assert "календарных дня" in roles["T"]["role_evidence"]
    assert "без трассировки" in roles["T"]["role_evidence"]


def node_record(gid, score, cluster=1, seed=False, role="transit", isolated=False):
    return {
        "node_id": gid, "priority_score": score, "role": role, "role_score": 0.75,
        "role_evidence": "Наблюдаемая роль подтверждается указанными переводами.",
        "is_seed": seed, "depth": None if isolated else 1, "seed_reach": 0 if isolated else 1,
        "fast_forward_fraction": 0 if isolated else 0.5, "truncated_by_depth": False,
        "features": {"community_id": cluster, "incoming_counterparties": 0 if isolated else 1,
            "outgoing_counterparties": 0 if isolated else 1,
            "total_incoming_amount": 0 if isolated else 100, "total_outgoing_amount": 0 if isolated else 80,
            "incoming_transaction_count": 0 if isolated else 2, "outgoing_transaction_count": 0 if isolated else 1,
            "pagerank": 0.1, "betweenness": 0.2},
    }


@pytest.fixture
def export_analysis():
    seed, candidate = "100000000000000001", "100000000000000002"
    nodes = {
        seed: node_record(seed, 99.9, seed=True, role="distributor"),
        candidate: node_record(candidate, 87.5),
        "Z": node_record("Z", 87.5, cluster=2),
        "000007": node_record("000007", 0, cluster=2, role="peripheral", isolated=True),
    }
    df = pd.DataFrame([(seed, candidate, 10.25), (candidate, "Z", 20), ("Z", "Z", 3.5)], columns=["sender", "receiver", "amount"])
    return SimpleNamespace(nodes=nodes, df=df)


def test_export_preserves_all_ids_and_scales_priority_once(export_analysis):
    frames = frames_for_analysis(export_analysis)
    nodes, top, clusters = frames["nodes_roles.csv"], frames["top_nodes.csv"], frames["clusters.csv"]
    assert set(nodes.gid) == set(export_analysis.nodes)
    assert nodes.gid.is_unique
    assert nodes.set_index("gid").loc["100000000000000002", "priority_score"] == 0.875
    assert nodes.set_index("gid").loc["100000000000000002", "role_score"] == 0.75
    assert list(top.gid) == ["100000000000000002", "Z", "000007"]
    assert list(top["rank"]) == [1, 2, 3]
    assert top.priority_score.is_monotonic_decreasing
    assert clusters.set_index("cluster_id").loc[1, "sum_kzt_internal"] == 10.25
    assert clusters.set_index("cluster_id").loc[2, "sum_kzt_internal"] == 3.5
    assert clusters.n_nodes.sum() == len(nodes)
    assert clusters.n_seed.sum() == 1
    assert all("Транзит" in text or "Распределитель" in text or "Роль не определена" in text for text in clusters.hypothesis)
    csv = nodes.to_csv(index=False)
    assert "100000000000000001" in csv and "100000000000000002" in csv and "000007" in csv
    assert "e+" not in csv.lower()
    assert export_analysis.nodes["100000000000000002"]["priority_score"] == 87.5


def test_zip_and_disk_exports_contain_only_three_consistent_csv_files(export_analysis, tmp_path):
    blob = zip_for_analysis(export_analysis)
    assert blob == zip_for_analysis(export_analysis)
    write_outputs(export_analysis, tmp_path)
    expected = {"nodes_roles.csv", "clusters.csv", "top_nodes.csv"}
    assert {p.name for p in tmp_path.iterdir()} == expected
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        assert set(archive.namelist()) == expected
        for name in expected:
            assert archive.read(name) == (tmp_path / name).read_bytes()
        restored = pd.read_csv(io.BytesIO(archive.read("nodes_roles.csv")), dtype={"gid": str})
        assert set(restored.gid) == set(export_analysis.nodes)


def test_top_fifty_excludes_seeds_and_breaks_ties_by_exact_gid():
    nodes = {f"{i:05}": node_record(f"{i:05}", 20, seed=i < 2, isolated=True) for i in range(65)}
    analysis = SimpleNamespace(nodes=nodes, df=pd.DataFrame(columns=["sender", "receiver", "amount"]))
    frames = frames_for_analysis(analysis)
    assert len(frames["nodes_roles.csv"]) == 65
    assert list(frames["top_nodes.csv"].gid) == [f"{i:05}" for i in range(2, 52)]
    for node in nodes.values():
        node["is_seed"] = True
    assert frames_for_analysis(analysis)["top_nodes.csv"].empty


def test_evidence_is_bounded_and_invalid_scores_are_rejected(export_analysis):
    node = export_analysis.nodes["Z"]
    node["role_evidence"] = "Основание " * 40
    roles = frames_for_analysis(export_analysis)["nodes_roles.csv"].set_index("gid")
    assert len(roles.loc["Z", "evidence"]) == 200
    for invalid in (float("nan"), float("inf"), -1, 101):
        node["priority_score"] = invalid
        with pytest.raises(ValueError):
            frames_for_analysis(export_analysis)


def test_subnormal_inflow_exports_missing_ratio_instead_of_infinity(export_analysis):
    node = export_analysis.nodes["Z"]
    node["features"]["total_incoming_amount"] = 1e-310
    node["features"]["total_outgoing_amount"] = 1e15
    nodes = frames_for_analysis(export_analysis)["nodes_roles.csv"].set_index("gid")
    assert pd.isna(nodes.loc["Z", "pass_through"])
    with zipfile.ZipFile(io.BytesIO(zip_for_analysis(export_analysis))) as archive:
        csv = archive.read("nodes_roles.csv").decode("utf-8")
        assert "inf" not in csv.lower()
        restored = pd.read_csv(io.StringIO(csv), dtype={"gid": str}).set_index("gid")
        assert pd.isna(restored.loc["Z", "pass_through"])
