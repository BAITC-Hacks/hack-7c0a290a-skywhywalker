"""Integration regressions for official data, honest timing and dataset isolation."""

import csv
import io
import json
import math
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.analysis import Analysis
from backend.datasets import OFFICIAL_FILES, load_dataset, load_official
from backend.main import app, store


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_DIRECTORY = ROOT / "data" / "official"
HAS_OFFICIAL = all((OFFICIAL_DIRECTORY / filename).is_file() for filename in OFFICIAL_FILES)
HEADER = "sender,receiver,amount,timestamp\n"
CSV_FILES = {"nodes_roles.csv", "clusters.csv", "top_nodes.csv"}


@pytest.fixture(scope="module")
def daily_analysis():
    # The same-day fan-in/fan-out would falsely trigger rapid forwarding if
    # midnight date containers were treated as measured transaction times.
    sources = ["9007199254740993", "S2", "S3", "S4", "S5", "S6"]
    rows = [f"{source},0007,100,2026-07-01" for source in sources]
    rows += [f"0007,{target},200,2026-07-01" for target in ("9007199254740995", "T2", "T3")]
    frame = load_dataset((HEADER + "\n".join(rows) + "\n").encode(), "daily.csv")
    metadata = {gid: {"is_seed": False, "depth": 1} for gid in set(frame.sender) | set(frame.receiver)}
    metadata["9007199254740993"] = {"is_seed": True, "depth": 0}
    metadata["9007199254740995"] = {"is_seed": False, "depth": 4}
    metadata["9007199254740997"] = {"is_seed": True, "depth": 0}  # Isolated.
    frame.attrs.update(node_metadata=metadata, currency="KZT", source_kind="official")
    return Analysis(frame, "synthetic_daily.csv")


@pytest.fixture(scope="module")
def official_analysis():
    if not HAS_OFFICIAL:
        pytest.skip("Официальные исходные Parquet-файлы не включены в репозиторий.")
    return Analysis(load_official(OFFICIAL_DIRECTORY), "official")


def assert_finite_json(analysis, evidence_nodes):
    text = json.dumps({
        "payload": analysis.payload(),
        "nodes": list(analysis.nodes.values()),
        "evidence": [analysis.evidence(node) for node in evidence_nodes],
    }, allow_nan=False)
    assert json.loads(text)["payload"]["stats"]["accounts"] == len(analysis.nodes)


def assert_consistent_score(node):
    weights = node["score_weights"]
    assert sum(weights.values()) == pytest.approx(1)
    assert weights["flow_score"] == 0
    assert node["component_availability"]["flow_score"] is False
    expected = sum(node["components"][key] * value for key, value in weights.items())
    expected *= node["priority_multiplier"]
    assert node["priority_score"] == pytest.approx(round(expected, 2), abs=1e-9)
    assert 0 <= node["priority_score"] <= 100


def test_daily_analysis_preserves_isolates_and_string_identifiers(daily_analysis):
    expected = set(daily_analysis.df.attrs["node_metadata"])
    assert set(daily_analysis.nodes) == expected
    assert set(daily_analysis.graph) == expected
    assert all(isinstance(gid, str) for gid in daily_analysis.nodes)
    assert {"0007", "9007199254740993", "9007199254740995", "9007199254740997"} <= expected
    isolated = daily_analysis.nodes["9007199254740997"]
    assert isolated["features"]["is_seed"] is True
    assert isolated["features"]["transaction_count"] == 0
    assert isolated["features"]["total_volume"] == 0
    assert isolated["features"]["in_out_ratio"] is None
    assert daily_analysis.graph.degree("9007199254740997") == 0
    assert daily_analysis.evidence("9007199254740997")["transactions"] == []
    assert daily_analysis.paths("9007199254740997") == []
    assert_finite_json(daily_analysis, expected)


def test_daily_dates_cannot_create_rapid_or_mule_claims(daily_analysis):
    for node in daily_analysis.nodes.values():
        feature = node["features"]
        assert feature["timing_available"] is False
        for key in ("matched_amount", "rapid_amount", "rapid_share", "average_holding_minutes"):
            assert feature[key] is None
        assert feature["rapid_pairs"] == []
        assert {"RAPID_PASS_THROUGH", "POTENTIAL_MULE_PATTERN"}.isdisjoint(node["patterns"])
        assert_consistent_score(node)
    # Multi-edge paths exist, but all transfers have the same calendar date.
    paths = daily_analysis.paths("0007", limit=20)
    sequences = [path for path in paths if len(path["nodes"]) >= 3]
    assert sequences
    assert all(path["chronological"] is not True for path in sequences)
    assert not any("time-ordered structural path" in path["interpretation"] for path in sequences)
    assert not any("FIFO <=60 minutes" in daily_analysis.evidence(gid)["methodology"] for gid in daily_analysis.nodes)


def test_mixed_date_and_timestamp_cannot_order_same_calendar_day_path():
    raw = (HEADER + "A,B,100,2026-07-01\nB,C,100,2026-07-01T12:00:00Z\n").encode()
    analysis = Analysis(load_dataset(raw, "mixed.csv"), "mixed.csv")
    assert analysis.metadata["time_precision"] == "day"
    path = next(path for path in analysis.paths("B") if path["nodes"] == ["A", "B", "C"])
    assert path["chronological"] is False
    assert "time-ordered structural path" not in path["interpretation"]


def test_seed_and_boundary_penalties_are_applied_to_reported_score(daily_analysis):
    assert daily_analysis.nodes["9007199254740993"]["priority_multiplier"] == pytest.approx(0.7)
    assert daily_analysis.nodes["9007199254740997"]["priority_multiplier"] == pytest.approx(0.7)
    boundary = daily_analysis.nodes["9007199254740995"]
    assert boundary["features"]["truncated_by_depth"] is True
    assert boundary["priority_multiplier"] == pytest.approx(0.65)
    assert daily_analysis.nodes["0007"]["priority_multiplier"] == 1
    for node in daily_analysis.nodes.values():
        assert_consistent_score(node)


def test_extreme_valid_amount_ratios_remain_json_safe():
    raw = (HEADER + "A,B,1e15,2026-07-01\nB,C,1e-300,2026-07-01\nC,D,1e15,2026-07-01\n").encode()
    analysis = Analysis(load_dataset(raw, "extreme.csv"), "extreme.csv")
    assert_finite_json(analysis, analysis.nodes)


@pytest.mark.parametrize("header,unit,absent_unit", [
    ("sender,receiver,amount,timestamp\n", "ед.", "₸"),
    ("src,dst,sum_kzt,date\n", "₸", "ед."),
])
def test_role_evidence_uses_only_known_currency(header, unit, absent_unit):
    raw = (header + "A,B,100,2026-07-01\nB,C,100,2026-07-02\n").encode()
    analysis = Analysis(load_dataset(raw, "currency.csv"), "currency.csv")
    assert analysis.nodes["B"]["role"] == "transit"
    assert unit in analysis.nodes["B"]["role_evidence"]
    assert all(absent_unit not in node["role_evidence"] for node in analysis.nodes.values())


def test_official_analysis_preserves_every_node_and_seed(official_analysis):
    analysis = official_analysis
    assert analysis.stats["accounts"] == 2248
    assert analysis.stats["transactions"] == 4840
    assert analysis.stats["links"] == 3119
    assert analysis.stats["total_volume"] == pytest.approx(365890012.01)
    assert set(analysis.nodes) == set(analysis.df.attrs["node_metadata"])
    assert all(isinstance(gid, str) for gid in analysis.nodes)
    assert any(int(gid) > 2**53 for gid in analysis.nodes)
    isolated = {gid for gid in analysis.graph if analysis.graph.degree(gid) == 0}
    assert len(isolated) == 19
    assert all(analysis.nodes[gid]["features"]["is_seed"] for gid in isolated)
    assert sum(node["features"]["is_seed"] for node in analysis.nodes.values()) == 81
    assert sum(node["features"]["truncated_by_depth"] for node in analysis.nodes.values()) == 444
    assert_finite_json(analysis, [analysis.ranking[0]["node_id"], *sorted(isolated)])
    for node in analysis.nodes.values():
        assert node["features"]["rapid_share"] is None
        assert {"RAPID_PASS_THROUGH", "POTENTIAL_MULE_PATTERN"}.isdisjoint(node["patterns"])
        assert_consistent_score(node)


@pytest.fixture(scope="module")
def unified_client():
    with pytest.MonkeyPatch.context() as patch:
        patch.delenv("OPENAI_API_KEY", raising=False)
        patch.delenv("MONEYGRAPH_DATA_DIR", raising=False)
        with TestClient(app) as client:
            yield client
    for key in list(store):
        if key not in {"demo", "official"}:
            del store[key]


def upload_and_analyze(client, filename, rows):
    response = client.post("/api/upload", files={"file": (filename, (HEADER + rows).encode(), "text/csv")})
    assert response.status_code == 200, response.text
    headers = {"X-Dataset-ID": response.json()["dataset_id"]}
    assert client.get("/api/graph", headers=headers).status_code == 409
    response = client.post("/api/analyze", headers=headers)
    assert response.status_code == 200, response.text
    return headers, response.json()


def exported_csvs(client, headers):
    response = client.get("/api/export", headers=headers)
    assert response.status_code == 200, response.text
    assert "zip" in response.headers["content-type"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == CSV_FILES
        assert len(archive.namelist()) == 3
        return {
            name: list(csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig"))))
            for name in CSV_FILES
        }


def assert_export_matches_graph(client, headers, graph):
    files = exported_csvs(client, headers)
    graph_nodes = {node["data"]["id"]: node["data"] for node in graph["nodes"]}
    exported_nodes = {row["gid"]: row for row in files["nodes_roles.csv"]}
    assert len(exported_nodes) == len(files["nodes_roles.csv"]) == graph["stats"]["accounts"]
    assert set(exported_nodes) == set(graph_nodes)
    for gid, row in exported_nodes.items():
        assert float(row["priority_score"]) == pytest.approx(graph_nodes[gid]["priority_score"] / 100, abs=1e-6)
        assert 0 < len(row["evidence"]) <= 200
        assert any(character.isdigit() for character in row["evidence"])
    cluster_response = client.get("/api/clusters", headers=headers)
    assert cluster_response.status_code == 200, cluster_response.text
    clusters = cluster_response.json()
    assert isinstance(clusters, list)
    assert sum(cluster["n_nodes"] for cluster in clusters) == len(graph_nodes)
    assert {str(cluster["cluster_id"]) for cluster in clusters} == {row["cluster_id"] for row in files["clusters.csv"]}
    assert sum(int(row["n_nodes"]) for row in files["clusters.csv"]) == len(graph_nodes)
    assert all(math.isfinite(cluster["sum_kzt_internal"]) for cluster in clusters)
    top = files["top_nodes.csv"]
    assert all(row["gid"] in exported_nodes for row in top)
    assert all(exported_nodes[row["gid"]]["is_seed"].lower() == "false" for row in top)
    priorities = [float(row["priority_score"]) for row in top]
    assert priorities == sorted(priorities, reverse=True)
    assert [int(row["rank"]) for row in top] == list(range(1, len(top) + 1))
    assert all(float(row["priority_score"]) == float(exported_nodes[row["gid"]]["priority_score"]) for row in top)
    return files


def test_api_builtin_datasets_and_default_selection(unified_client):
    response = unified_client.get("/api/datasets")
    assert response.status_code == 200
    datasets = response.json()
    assert isinstance(datasets, list)
    by_id = {item["id"]: item for item in datasets}
    assert "demo" in by_id
    assert ("official" in by_id) is HAS_OFFICIAL
    expected_default = "official" if HAS_OFFICIAL else "demo"
    assert datasets[0]["id"] == expected_default
    default_graph = unified_client.get("/api/graph")
    selected_graph = unified_client.get("/api/graph", headers={"X-Dataset-ID": expected_default})
    assert default_graph.status_code == selected_graph.status_code == 200
    assert default_graph.json() == selected_graph.json()
    demo = unified_client.get("/api/graph", headers={"X-Dataset-ID": "demo"})
    assert demo.status_code == 200
    assert demo.json()["stats"]["transactions"] == 172


def test_api_defaults_to_demo_when_official_files_unavailable(tmp_path, monkeypatch):
    previous_store = dict(store)
    monkeypatch.setenv("MONEYGRAPH_DATA_DIR", str(tmp_path / "not-present"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    try:
        with TestClient(app) as client:
            response = client.get("/api/datasets")
            assert response.status_code == 200
            assert [item["id"] for item in response.json()] == ["demo"]
            graph = client.get("/api/graph")
            assert graph.status_code == 200
            assert graph.json()["stats"]["transactions"] == 172
            assert client.get("/api/graph", headers={"X-Dataset-ID": "official"}).status_code == 404
    finally:
        store.clear()
        store.update(previous_store)


def test_api_exports_use_selected_dataset_without_cross_contamination(unified_client):
    first_headers, first_graph = upload_and_analyze(
        unified_client, "first.csv", "0007,9007199254740993,100,2026-07-01T12:00:00Z\n",
    )
    second_headers, second_graph = upload_and_analyze(
        unified_client, "second.csv", "X,Y,20,2026-07-02\nY,Z,15,2026-07-02\n",
    )
    assert first_headers != second_headers
    first_export = assert_export_matches_graph(unified_client, first_headers, first_graph)
    second_export = assert_export_matches_graph(unified_client, second_headers, second_graph)
    assert {row["gid"] for row in first_export["nodes_roles.csv"]} == {"0007", "9007199254740993"}
    assert {row["gid"] for row in second_export["nodes_roles.csv"]} == {"X", "Y", "Z"}
    # Switching to another dataset must not mutate the first dataset's export.
    assert exported_csvs(unified_client, first_headers) == first_export
    assert unified_client.get("/api/export", headers={"X-Dataset-ID": "missing-dataset"}).status_code == 404


@pytest.mark.skipif(not HAS_OFFICIAL, reason="Официальные исходные данные отсутствуют.")
def test_api_official_export_contains_full_population_and_nonseed_ranking(unified_client):
    headers = {"X-Dataset-ID": "official"}
    response = unified_client.get("/api/graph", headers=headers)
    assert response.status_code == 200
    files = assert_export_matches_graph(unified_client, headers, response.json())
    nodes = files["nodes_roles.csv"]
    assert len(nodes) == 2248
    assert sum(row["is_seed"].lower() == "true" for row in nodes) == 81
    isolated = [row for row in nodes if int(row["in_tx"]) == int(row["out_tx"]) == 0]
    assert len(isolated) == 19
    assert all(row["is_seed"].lower() == "true" for row in isolated)
    assert len(files["top_nodes.csv"]) >= 20
