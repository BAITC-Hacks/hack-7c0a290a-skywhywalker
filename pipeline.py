#!/usr/bin/env python3
"""Reproducible, explainable analysis of the four-hop transfer graph."""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd


ROLES = {"consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"}
REQUIRED = {
    "nodes": {"gid", "depth", "is_seed"},
    "edges": {"src", "dst", "sum_kzt", "n_tx", "depth"},
    "transactions": {"src", "dst", "date", "sum_kzt"},
}


def load_data(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frames = {name: pd.read_parquet(data_dir / f"{name}.parquet") for name in REQUIRED}
    for name, required in REQUIRED.items():
        missing = required - set(frames[name].columns)
        if missing:
            raise ValueError(f"{name}.parquet is missing: {sorted(missing)}")
    nodes, edges, tx = frames["nodes"], frames["edges"], frames["transactions"]
    if nodes.gid.duplicated().any() or edges.duplicated(["src", "dst"]).any():
        raise ValueError("Duplicate gids or src/dst edge pairs")
    gids = set(nodes.gid)
    if not set(edges.src).issubset(gids) or not set(edges.dst).issubset(gids):
        raise ValueError("An edge references a gid absent from nodes.parquet")
    if (edges.sum_kzt < 0).any() or (tx.sum_kzt < 0).any():
        raise ValueError("Negative transfer amounts are not supported")
    tx = tx.copy()
    tx["date"] = pd.to_datetime(tx["date"])
    check = tx.groupby(["src", "dst"], as_index=False).agg(
        computed_kzt=("sum_kzt", "sum"), computed_n_tx=("sum_kzt", "size")
    )
    merged = edges.merge(check, on=["src", "dst"], how="outer", indicator=True)
    if not (merged._merge == "both").all() or not np.allclose(
        merged.sum_kzt, merged.computed_kzt, rtol=1e-8, atol=0.01
    ) or not (merged.n_tx == merged.computed_n_tx).all():
        raise ValueError("edges.parquet and transactions.parquet disagree")
    return nodes, edges, tx


def make_graph(nodes: pd.DataFrame, edges: pd.DataFrame) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_nodes_from(int(gid) for gid in nodes.gid)
    for row in edges.itertuples(index=False):
        graph.add_edge(
            int(row.src), int(row.dst), sum_kzt=float(row.sum_kzt), n_tx=int(row.n_tx)
        )
    return graph


def rank01(values: pd.Series) -> pd.Series:
    """Percentile rank keeps very large transfers from swallowing other signals."""
    return values.rank(pct=True, method="average").fillna(0).clip(0, 1)


def seed_reach(graph: nx.DiGraph, seeds: list[int]) -> dict[int, int]:
    """Number of known seeds that can reach each node within four directed hops."""
    counts = defaultdict(int)
    for seed in seeds:
        visited = {seed}
        queue = deque([(seed, 0)])
        while queue:
            node, depth = queue.popleft()
            counts[node] += 1
            if depth >= 4:
                continue
            for successor in graph.successors(node):
                if successor not in visited:
                    visited.add(successor)
                    queue.append((successor, depth + 1))
    return counts


def fast_forward_fraction(tx: pd.DataFrame) -> dict[int, float]:
    """Share of incoming transfers followed by any outgoing transfer in 0–2 days.

    This is a timing indicator, not transaction-level money tracing.
    """
    incoming = defaultdict(list)
    outgoing = defaultdict(list)
    for row in tx.itertuples(index=False):
        incoming[int(row.dst)].append(row.date)
        outgoing[int(row.src)].append(row.date)
    fractions = {}
    for gid, dates in incoming.items():
        exits = sorted(outgoing.get(gid, []))
        if not exits:
            fractions[gid] = 0.0
            continue
        exit_dates = np.array(exits, dtype="datetime64[ns]")
        arrivals = np.array(dates, dtype="datetime64[ns]")
        positions = np.searchsorted(exit_dates, arrivals, side="left")
        matched = sum(
            pos < len(exit_dates)
            and exit_dates[pos] - arrival <= np.timedelta64(2, "D")
            for pos, arrival in zip(positions, arrivals)
        )
        fractions[gid] = matched / len(dates)
    return fractions


def cluster_graph(graph: nx.DiGraph) -> dict[int, int]:
    undirected = nx.Graph()
    undirected.add_nodes_from(graph.nodes)
    for src, dst, attrs in graph.edges(data=True):
        weight = np.log1p(attrs["sum_kzt"])
        if undirected.has_edge(src, dst):
            undirected[src][dst]["weight"] += weight
        else:
            undirected.add_edge(src, dst, weight=weight)
    communities = nx.community.louvain_communities(undirected, weight="weight", seed=42)
    communities = sorted(communities, key=lambda members: (-len(members), min(members)))
    return {int(gid): cluster_id for cluster_id, members in enumerate(communities, 1) for gid in members}


def calculate_features(
    graph: nx.DiGraph, nodes: pd.DataFrame, tx: pd.DataFrame
) -> pd.DataFrame:
    df = nodes[["gid", "depth", "is_seed"]].copy()
    df["gid"] = df.gid.astype("int64")
    df["in_deg"] = df.gid.map(dict(graph.in_degree())).astype(int)
    df["out_deg"] = df.gid.map(dict(graph.out_degree())).astype(int)
    df["in_kzt"] = df.gid.map(dict(graph.in_degree(weight="sum_kzt"))).astype(float)
    df["out_kzt"] = df.gid.map(dict(graph.out_degree(weight="sum_kzt"))).astype(float)
    df["in_tx"] = df.gid.map(dict(graph.in_degree(weight="n_tx"))).astype(int)
    df["out_tx"] = df.gid.map(dict(graph.out_degree(weight="n_tx"))).astype(int)
    df["pagerank"] = df.gid.map(nx.pagerank(graph, weight="sum_kzt")).astype(float)
    # Directed betweenness distinguishes connectors; approximate sampling keeps reruns fast.
    sample_size = min(160, graph.number_of_nodes())
    df["betweenness"] = df.gid.map(
        nx.betweenness_centrality(graph, k=sample_size, normalized=True, seed=42)
    ).astype(float)
    df["seed_reach"] = df.gid.map(
        seed_reach(graph, df.loc[df.is_seed, "gid"].astype(int).tolist())
    ).fillna(0).astype(int)
    df["fast_forward"] = df.gid.map(fast_forward_fraction(tx)).fillna(0).astype(float)
    df["pass_through"] = np.where(df.in_kzt > 0, df.out_kzt / df.in_kzt, np.nan)
    df["retention"] = np.where(
        (df.in_kzt > 0) & (~df.is_seed),
        np.clip(1 - df.out_kzt / df.in_kzt.replace(0, np.nan), 0, 1),
        np.nan,
    )
    df["truncated_by_depth"] = (df.depth == 4) & (df.out_deg == 0)
    df["cluster_id"] = df.gid.map(cluster_graph(graph)).astype(int)
    return df


def assign_roles(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    centrality_cut = df.loc[df.betweenness > 0, "betweenness"].quantile(0.92)
    amount_cut = df.loc[df.in_kzt > 0, "in_kzt"].quantile(0.50)
    roles, confidences, evidence = [], [], []
    for r in df.itertuples(index=False):
        ratio = r.pass_through
        connector = (
            r.in_deg >= 2 and r.out_deg >= 2 and r.seed_reach >= 2
            and r.betweenness >= centrality_cut and r.betweenness > 0
        )
        collector = (
            not r.is_seed and r.in_deg >= 3 and r.in_kzt >= amount_cut
            and r.retention >= 0.35
        )
        distributor = (
            r.out_deg >= 5 and r.out_kzt > 0
            and (r.is_seed or r.in_deg <= max(2, r.out_deg // 2))
        )
        transit = (
            not r.is_seed and r.in_deg >= 1 and r.out_deg >= 1
            and pd.notna(ratio) and 0.65 <= ratio <= 1.5
        )
        if r.truncated_by_depth:
            role = "peripheral"
            score = 0.50
            reason = f"Глубина 4: исходящие обрезаны выгрузкой; получено {r.in_kzt:,.0f} ₸, статус получателя неизвестен."
        elif r.is_seed and r.out_deg == 0:
            role = "peripheral"
            score = 0.50
            reason = f"Исходный seed без наблюдаемых исходящих; входящих плательщиков в графе: {r.in_deg}."
        elif connector:
            role = "coordinator"
            score = min(0.95, 0.62 + 0.035 * min(r.in_deg + r.out_deg, 8) + 0.02 * min(r.seed_reach, 3))
            reason = f"Между потоками: {r.in_deg} вход., {r.out_deg} исход.; достижим из {r.seed_reach} seed, посредничество {r.betweenness:.4f}."
        elif collector:
            role = "consolidator"
            score = min(0.96, 0.57 + 0.04 * min(r.in_deg, 6) + 0.16 * r.retention)
            reason = f"Получил {r.in_kzt:,.0f} ₸ от {r.in_deg} плательщиков; внутри графа удержано {r.retention:.0%}."
        elif distributor:
            role = "distributor"
            score = min(0.94, 0.57 + 0.035 * min(r.out_deg, 8))
            reason = f"Отправил {r.out_kzt:,.0f} ₸ {r.out_deg} получателям; входящих плательщиков: {r.in_deg}."
        elif transit:
            role = "transit"
            score = min(0.94, 0.55 + 0.2 * (1 - min(abs(ratio - 1), 0.5)) + 0.1 * r.fast_forward)
            reason = f"Получил {r.in_kzt:,.0f} ₸, отправил {r.out_kzt:,.0f} ₸ ({ratio:.0%}); быстрый выход: {r.fast_forward:.0%} входов."
        elif r.out_deg == 0 and r.in_deg > 0 and r.depth < 4:
            role = "terminal"
            score = 0.65 + 0.10 * min(r.in_deg / 4, 1)
            reason = f"Получил {r.in_kzt:,.0f} ₸ от {r.in_deg} плательщиков; исходящих в наблюдаемой сети нет, глубина {r.depth}."
        else:
            role = "peripheral"
            score = 0.55
            reason = f"Недостаточно признаков: {r.in_deg} вход., {r.out_deg} исход., глубина {r.depth}."
        roles.append(role)
        confidences.append(round(float(score), 4))
        evidence.append(reason[:200])
    df["role"] = roles
    df["role_score"] = confidences
    df["evidence"] = evidence
    return df


def assign_priority(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    central = 0.55 * rank01(df.betweenness) + 0.45 * rank01(df.pagerank)
    traffic = rank01(np.log1p(df.in_kzt + df.out_kzt))
    reach = rank01(df.seed_reach)
    structure = 0.5 * rank01(df.in_deg) + 0.5 * rank01(df.out_deg)
    role_signal = df.role.map({
        "coordinator": 1.0, "consolidator": 0.95, "distributor": 0.85,
        "transit": 0.72, "terminal": 0.40, "peripheral": 0.10,
    }).astype(float)
    score = 0.25 * central + 0.22 * traffic + 0.20 * reach + 0.18 * structure + 0.15 * role_signal
    # Seeds are already known to investigators. Four-hop leaves have unobserved exits.
    score = score * np.where(df.is_seed, 0.7, 1) * np.where(df.truncated_by_depth, 0.65, 1)
    df["priority_score"] = score.clip(0, 1).round(4)
    return df


def make_clusters(df: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    edge_clusters = edges.assign(
        source_cluster=edges.src.map(df.set_index("gid").cluster_id),
        target_cluster=edges.dst.map(df.set_index("gid").cluster_id),
    )
    internal = edge_clusters.loc[
        edge_clusters.source_cluster == edge_clusters.target_cluster
    ].groupby("source_cluster").sum_kzt.sum()
    records = []
    for cluster_id, group in df.groupby("cluster_id"):
        leaders = group.sort_values("priority_score", ascending=False).head(5)
        role_counts = group.role.value_counts()
        prominent = role_counts.index[0]
        if group.is_seed.any():
            hypothesis = f"Сегмент с {int(group.is_seed.sum())} исходными seed; преобладают {prominent}."
        else:
            hypothesis = f"Сегмент без наблюдаемых seed; преобладают {prominent}."
        records.append({
            "cluster_id": int(cluster_id), "n_nodes": len(group),
            "n_seed": int(group.is_seed.sum()),
            "sum_kzt_internal": round(float(internal.get(cluster_id, 0)), 2),
            "top_gids": ",".join(str(int(gid)) for gid in leaders.gid),
            "hypothesis": hypothesis,
        })
    return pd.DataFrame(records).sort_values("cluster_id")


def write_outputs(df: pd.DataFrame, edges: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    export = df[[
        "gid", "role", "role_score", "cluster_id", "priority_score", "evidence",
        "depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "in_tx",
        "out_tx", "pagerank", "betweenness", "seed_reach", "fast_forward",
        "pass_through", "truncated_by_depth",
    ]].sort_values("gid")
    export.to_csv(out_dir / "nodes_roles.csv", index=False)
    make_clusters(df, edges).to_csv(out_dir / "clusters.csv", index=False)
    top = df.loc[~df.is_seed].sort_values(
        ["priority_score", "gid"], ascending=[False, True]
    ).head(50).copy()
    top.insert(0, "rank", range(1, len(top) + 1))
    top["why"] = top.apply(
        lambda row: f"{row.evidence} Достижим из {row.seed_reach} seed. Приоритет {row.priority_score:.3f}.",
        axis=1,
    )
    top[["rank", "gid", "role", "priority_score", "why"]].to_csv(
        out_dir / "top_nodes.csv", index=False
    )


def verify_outputs(nodes: pd.DataFrame, out_dir: Path) -> None:
    roles = pd.read_csv(out_dir / "nodes_roles.csv")
    clusters = pd.read_csv(out_dir / "clusters.csv")
    top = pd.read_csv(out_dir / "top_nodes.csv")
    assert len(roles) == len(nodes) and roles.gid.is_unique
    assert set(roles.role).issubset(ROLES)
    assert roles[["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]].notna().all().all()
    assert roles.evidence.str.len().between(1, 200).all()
    assert roles.role_score.between(0, 1).all() and roles.priority_score.between(0, 1).all()
    assert set(roles.cluster_id) == set(clusters.cluster_id)
    assert len(top) >= 20 and top.priority_score.is_monotonic_decreasing


def main() -> None:
    parser = argparse.ArgumentParser(description="Build MoneyMap AML analysis CSV files")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args()
    nodes, edges, tx = load_data(args.data)
    graph = make_graph(nodes, edges)
    features = calculate_features(graph, nodes, tx)
    result = assign_priority(assign_roles(features))
    write_outputs(result, edges, args.out)
    verify_outputs(nodes, args.out)
    print(f"OK: {len(nodes)} nodes, {len(edges)} edges, {len(tx)} transactions")
    print(f"Roles: {result.role.value_counts().to_dict()}")
    print(f"Clusters: {result.cluster_id.nunique()}; CSV output: {args.out.resolve()}")


if __name__ == "__main__":
    main()
