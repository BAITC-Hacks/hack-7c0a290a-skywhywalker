"""The team's six explainable roles, with explicit extraction-boundary guards.

The calendar timing signal is an association between dates. It neither matches
amounts nor establishes that an outgoing transfer contains the incoming money.
"""

from bisect import bisect_left
from collections import defaultdict
import math

import networkx as nx
import pandas as pd


ROLE_NAMES = {
    "coordinator": "Координатор",
    "consolidator": "Консолидация",
    "distributor": "Распределитель",
    "transit": "Транзит",
    "terminal": "Получатель без видимого выхода",
    "peripheral": "Роль не определена",
}
ROLES = frozenset(ROLE_NAMES)


def _finite(value, default=0.0):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _depth(value):
    number = _finite(value, None)
    return int(number) if number is not None and number >= 0 and number.is_integer() else None


def _seed(value):
    return str(value).strip().lower() in {"true", "1"}


def _seed_reach(graph, seeds):
    counts = defaultdict(int)
    for seed in sorted(seeds):
        if seed in graph:
            for gid in nx.single_source_shortest_path_length(graph, seed, cutoff=4):
                counts[gid] += 1
    return counts


def _calendar_forward_fractions(df):
    incoming, outgoing = defaultdict(list), defaultdict(list)
    for row in df.itertuples(index=False):
        if row.sender == row.receiver:
            continue
        # Normalized timestamps are UTC; do not invent intraday order for dates.
        day = pd.Timestamp(row.timestamp).date().toordinal()
        incoming[row.receiver].append(day)
        outgoing[row.sender].append(day)
    result = {}
    for gid, arrivals in incoming.items():
        exits = sorted(outgoing.get(gid, []))
        matched = 0
        for arrival in arrivals:
            position = bisect_left(exits, arrival)
            matched += position < len(exits) and exits[position] - arrival <= 2
        result[gid] = float(matched / len(arrivals))
    return result


def assign_roles(features: dict[str, dict], graph: nx.DiGraph, df: pd.DataFrame) -> dict[str, dict]:
    """Return JSON-safe role facts for every account, including isolated nodes.

    Thresholds and rule ordering derive from the team's MoneyMap pipeline.
    Unknown extraction depth cannot establish a terminal recipient. Calendar
    forward fractions use external incoming transfer counts, not their amounts.
    """
    metadata = df.attrs.get("node_metadata", {})
    unit = "₸" if df.attrs.get("currency") == "KZT" else "ед."
    seeds = {gid for gid in features if _seed(metadata.get(gid, {}).get("is_seed", False))}
    reach = _seed_reach(graph, seeds)
    forward = _calendar_forward_fractions(df)
    positive_centralities = [_finite(f.get("betweenness")) for f in features.values() if _finite(f.get("betweenness")) > 0]
    positive_amounts = [_finite(f.get("total_incoming_amount")) for f in features.values() if _finite(f.get("total_incoming_amount")) > 0]
    centrality_cut = float(pd.Series(positive_centralities).quantile(0.92)) if positive_centralities else math.inf
    amount_cut = float(pd.Series(positive_amounts).quantile(0.50)) if positive_amounts else math.inf
    result = {}
    for gid in sorted(features):
        feature = features[gid]
        depth = _depth(metadata.get(gid, {}).get("depth"))
        is_seed = gid in seeds
        in_deg = int(_finite(feature.get("incoming_counterparties")))
        out_deg = int(_finite(feature.get("outgoing_counterparties")))
        incoming = _finite(feature.get("total_incoming_amount"))
        outgoing = _finite(feature.get("total_outgoing_amount"))
        between = _finite(feature.get("betweenness"))
        seed_count = int(reach.get(gid, 0))
        fast_forward = float(forward.get(gid, 0.0))
        ratio = _finite(outgoing / incoming, None) if incoming > 0 else None
        retention = min(1.0, max(0.0, 1 - ratio)) if ratio is not None and not is_seed else None
        truncated = depth == 4 and out_deg == 0
        connector = in_deg >= 2 and out_deg >= 2 and seed_count >= 2 and between >= centrality_cut and between > 0
        collector = not is_seed and in_deg >= 3 and incoming >= amount_cut and retention is not None and retention >= 0.35
        distributor = out_deg >= 5 and outgoing > 0 and (is_seed or in_deg <= max(2, out_deg // 2))
        transit = not is_seed and in_deg >= 1 and out_deg >= 1 and ratio is not None and 0.65 <= ratio <= 1.5

        if truncated:
            role, score = "peripheral", 0.50
            reason = f"Глубина 4: исходящие обрезаны выгрузкой; получено {incoming:,.0f} {unit}; статус получателя неизвестен."
        elif is_seed and out_deg == 0:
            role, score = "peripheral", 0.50
            reason = f"Исходный клиент без наблюдаемых исходящих; входящих плательщиков в графе: {in_deg}."
        elif depth is None and out_deg == 0:
            role, score = "peripheral", 0.50
            reason = f"Наблюдаемых плательщиков: {in_deg}, получателей: {out_deg}. Глубина и границы наблюдения неизвестны; конечный получатель не установлен."
        elif connector:
            role = "coordinator"
            score = min(0.95, 0.62 + 0.035 * min(in_deg + out_deg, 8) + 0.02 * min(seed_count, 3))
            reason = f"Между потоками: {in_deg} вход., {out_deg} исход.; достижим из {seed_count} исходных клиентов, посредничество {between:.4f}."
        elif collector:
            role = "consolidator"
            score = min(0.96, 0.57 + 0.04 * min(in_deg, 6) + 0.16 * retention)
            reason = f"Получил {incoming:,.0f} {unit} от {in_deg} плательщиков; разница входа и выхода внутри выгрузки: {retention:.0%} входа."
        elif distributor:
            role = "distributor"
            score = min(0.94, 0.57 + 0.035 * min(out_deg, 8))
            reason = f"Отправил {outgoing:,.0f} {unit} {out_deg} получателям; входящих плательщиков: {in_deg}."
        elif transit:
            role = "transit"
            score = min(0.94, 0.55 + 0.2 * (1 - min(abs(ratio - 1), 0.5)) + 0.1 * fast_forward)
            reason = f"Получил {incoming:,.0f} {unit}, отправил {outgoing:,.0f} {unit} ({ratio:.0%}); выход в 0–2 календарных дня после {fast_forward:.0%} входов, без трассировки денег."
        elif out_deg == 0 and in_deg > 0 and depth is not None and depth < 4:
            role = "terminal"
            score = 0.65 + 0.10 * min(in_deg / 4, 1)
            reason = f"Получил {incoming:,.0f} {unit} от {in_deg} плательщиков; исходящих в наблюдаемой сети нет, глубина {depth}. За границами выгрузки переводы неизвестны."
        else:
            role, score = "peripheral", 0.55
            reason = f"Недостаточно признаков: {in_deg} вход., {out_deg} исход.; глубина {depth if depth is not None else 'неизвестна'}."

        result[gid] = {
            "role": role,
            "role_score": round(float(score), 4),
            "role_evidence": reason[:200],
            "is_seed": bool(is_seed),
            "depth": depth,
            "seed_reach": seed_count,
            "fast_forward_fraction": fast_forward,
            "truncated_by_depth": bool(truncated),
            "retention_ratio": retention,
            "pass_through_ratio": ratio,
        }
    return result
