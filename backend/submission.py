"""Produce the team's three CSV deliverables from one in-memory analysis.

Account IDs remain strings throughout. The UI priority scale 0..100 is divided
by 100 for the submission scale 0..1; no second ranking model is calculated.
"""

from collections import Counter, defaultdict
import io
import math
from pathlib import Path
import zipfile

import pandas as pd

from .roles_engine import ROLE_NAMES, ROLES


NODE_COLUMNS = [
    "gid", "role", "role_score", "cluster_id", "priority_score", "evidence",
    "depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "in_tx",
    "out_tx", "pagerank", "betweenness", "seed_reach", "fast_forward",
    "pass_through", "truncated_by_depth",
]
CLUSTER_COLUMNS = ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"]
TOP_COLUMNS = ["rank", "gid", "role", "priority_score", "why"]


def _number(value, field):
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Некорректное значение {field} при экспорте") from exc
    if not math.isfinite(number):
        raise ValueError(f"Неконечное значение {field} при экспорте")
    return number


def _integer(value, field):
    number = _number(value, field)
    if not number.is_integer() or number < 0:
        raise ValueError(f"Ожидалось неотрицательное целое {field}")
    return int(number)


def _fraction(value, field):
    number = _number(value, field)
    if not 0 <= number <= 1:
        raise ValueError(f"Значение {field} должно быть в диапазоне 0..1")
    return number


def _fact(node, name, default=None):
    return node.get(name, node.get("features", {}).get(name, default))


def _node_record(gid, node):
    if not isinstance(gid, str) or not gid:
        raise ValueError("GID при экспорте должен быть непустой строкой")
    feature = node["features"]
    role = node["role"]
    if role not in ROLES:
        raise ValueError(f"Неизвестная роль при экспорте: {role}")
    evidence = str(node.get("role_evidence", "")).strip()[:200]
    if not evidence:
        raise ValueError("Для роли требуется непустое численное основание")
    priority = _number(node["priority_score"], "priority_score")
    if not 0 <= priority <= 100:
        raise ValueError("Приоритет интерфейса должен быть в диапазоне 0..100")
    incoming = _number(feature.get("total_incoming_amount", 0), "in_kzt")
    outgoing = _number(feature.get("total_outgoing_amount", 0), "out_kzt")
    pass_through = outgoing / incoming if incoming > 0 else None
    if pass_through is not None and not math.isfinite(pass_through):
        pass_through = None
    depth = _fact(node, "depth")
    return {
        "gid": gid,
        "role": role,
        "role_score": _fraction(node["role_score"], "role_score"),
        "cluster_id": _integer(feature["community_id"], "cluster_id"),
        "priority_score": round(priority / 100, 6),
        "evidence": evidence,
        "depth": _integer(depth, "depth") if depth is not None else None,
        "is_seed": str(_fact(node, "is_seed", False)).lower() in {"true", "1"},
        "in_deg": _integer(feature.get("incoming_counterparties", 0), "in_deg"),
        "out_deg": _integer(feature.get("outgoing_counterparties", 0), "out_deg"),
        "in_kzt": incoming,
        "out_kzt": outgoing,
        "in_tx": _integer(feature.get("incoming_transaction_count", 0), "in_tx"),
        "out_tx": _integer(feature.get("outgoing_transaction_count", 0), "out_tx"),
        "pagerank": _number(feature.get("pagerank", 0), "pagerank"),
        "betweenness": _number(feature.get("betweenness", 0), "betweenness"),
        "seed_reach": _integer(_fact(node, "seed_reach", 0), "seed_reach"),
        "fast_forward": _fraction(_fact(node, "fast_forward_fraction", 0), "fast_forward"),
        "pass_through": pass_through,
        "truncated_by_depth": str(_fact(node, "truncated_by_depth", False)).lower() in {"true", "1"},
    }


def frames_for_analysis(analysis) -> dict[str, pd.DataFrame]:
    """Return all roles, cluster summaries and up to 50 non-seed candidates.

    Small generic datasets may contain fewer than 20 candidates. Isolated
    accounts are taken from analysis.nodes, never reconstructed from transfers.
    """
    records = [_node_record(gid, analysis.nodes[gid]) for gid in sorted(analysis.nodes)]
    nodes = pd.DataFrame(records, columns=NODE_COLUMNS)
    nodes["gid"] = nodes["gid"].astype("string")
    nodes["depth"] = pd.array(nodes["depth"], dtype="Int64")
    by_gid = {record["gid"]: record for record in records}
    grouped = defaultdict(list)
    for record in records:
        grouped[record["cluster_id"]].append(record)
    internal = defaultdict(list)
    for row in analysis.df.itertuples(index=False):
        if row.sender not in by_gid or row.receiver not in by_gid:
            raise ValueError("Транзакция ссылается на отсутствующий в анализе GID")
        cluster = by_gid[row.sender]["cluster_id"]
        if cluster == by_gid[row.receiver]["cluster_id"]:
            internal[cluster].append(_number(row.amount, "amount"))
    clusters = []
    for cluster, members in sorted(grouped.items()):
        leaders = sorted(members, key=lambda r: (-r["priority_score"], r["gid"]))[:5]
        counts = Counter(r["role"] for r in members)
        prominent = min(counts, key=lambda role: (-counts[role], role))
        seeds = sum(r["is_seed"] for r in members)
        clusters.append({
            "cluster_id": cluster,
            "n_nodes": len(members),
            "n_seed": seeds,
            "sum_kzt_internal": round(math.fsum(internal[cluster]), 2),
            "top_gids": ",".join(r["gid"] for r in leaders),
            "hypothesis": f"Исходных клиентов: {seeds}. Преобладает роль «{ROLE_NAMES[prominent]}». Это структурная гипотеза для проверки.",
        })
    candidates = sorted((r for r in records if not r["is_seed"]), key=lambda r: (-r["priority_score"], r["gid"]))[:50]
    top = [{
        "rank": rank,
        "gid": record["gid"],
        "role": record["role"],
        "priority_score": record["priority_score"],
        "why": f"{record['evidence']} Достижим из {record['seed_reach']} исходных клиентов. Приоритет {record['priority_score']:.4f}.",
    } for rank, record in enumerate(candidates, 1)]
    top_frame = pd.DataFrame(top, columns=TOP_COLUMNS)
    top_frame["gid"] = top_frame["gid"].astype("string")
    return {
        "nodes_roles.csv": nodes,
        "clusters.csv": pd.DataFrame(clusters, columns=CLUSTER_COLUMNS),
        "top_nodes.csv": top_frame,
    }


def zip_for_analysis(analysis) -> bytes:
    """Build the CSV bundle in memory, without app files or configuration."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, frame in frames_for_analysis(analysis).items():
            entry = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, frame.to_csv(index=False, lineterminator="\n").encode("utf-8"))
    return output.getvalue()


def write_outputs(analysis, out_dir) -> None:
    """Write only the three documented CSV files to the requested directory."""
    frames = frames_for_analysis(analysis)
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    for filename, frame in frames.items():
        (target / filename).write_text(frame.to_csv(index=False, lineterminator="\n"), encoding="utf-8", newline="")
