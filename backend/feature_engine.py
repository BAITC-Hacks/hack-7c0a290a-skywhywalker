import numpy as np
import networkx as nx
from .graph_engine import timing_features


def calculate_features(df, graph):
    # Team MVP: combine reciprocal directions on a log-weighted projection.
    undirected = nx.Graph()
    undirected.add_nodes_from(graph)
    for a, b, data in graph.edges(data=True):
        weight = float(np.log1p(data['weight']))
        if undirected.has_edge(a, b):
            undirected[a][b]['weight'] += weight
        else:
            undirected.add_edge(a, b, weight=weight)
    groups = (nx.community.louvain_communities(undirected, weight='weight', seed=42)
              if graph.number_of_edges() else [{n} for n in graph])
    groups = sorted(groups, key=lambda group: (-len(group), min(group)))
    community = {n: i + 1 for i, group in enumerate(groups) for n in group}
    centrality = nx.degree_centrality(graph)
    between = nx.betweenness_centrality(graph, k=min(100,len(graph)) if len(graph)>250 else None, seed=42)
    pagerank = nx.pagerank(graph, weight='weight', max_iter=1000)
    data = df.copy(deep=False)
    data.attrs = {}
    incoming_groups = {n: g for n, g in data.groupby('receiver', sort=False)}
    outgoing_groups = {n: g for n, g in data.groupby('sender', sort=False)}
    linked_indices = {}
    for row in df.itertuples():
        for n in {row.sender, row.receiver}:
            linked_indices.setdefault(n, []).append(row.Index)
    empty = data.iloc[:0]
    metadata = df.attrs.get('node_metadata', {})
    result = {}
    for n in sorted(graph):
        inc, out = incoming_groups.get(n, empty), outgoing_groups.get(n, empty)
        linked = data.loc[linked_indices.get(n, [])]
        linked.attrs = {'time_precision':df.attrs.get('time_precision','timestamp')}
        incoming, outgoing = float(inc.amount.sum()), float(out.amount.sum())
        ratio = incoming/outgoing if outgoing else None
        ratio = ratio if ratio is not None and np.isfinite(ratio) else None
        neighbors = (set(graph.predecessors(n)) | set(graph.successors(n))) - {n}
        info = metadata.get(n, {})
        result[n] = {
            'incoming_transaction_count':len(inc), 'outgoing_transaction_count':len(out),
            'transaction_count':len(linked),
            'incoming_counterparties':len(set(inc.sender)-{n}), 'outgoing_counterparties':len(set(out.receiver)-{n}),
            'total_incoming_amount':incoming, 'total_outgoing_amount':outgoing,
            'total_volume':float(linked.amount.sum()), 'in_out_ratio':ratio,
            'turnover_ratio':min(incoming,outgoing)/max(incoming,outgoing) if max(incoming,outgoing) else 0,
            'degree_centrality':centrality[n], 'in_degree':graph.in_degree(n), 'out_degree':graph.out_degree(n),
            'betweenness':between[n], 'pagerank':pagerank[n], 'community_id':community[n],
            'average_incoming_amount':float(inc.amount.mean()) if len(inc) else 0,
            'average_outgoing_amount':float(out.amount.mean()) if len(out) else 0,
            'median_amount':float(linked.amount.median()) if len(linked) else 0,
            'communities_connected':len({community[v] for v in neighbors}),
            'is_seed':bool(info.get('is_seed', False)), 'depth':info.get('depth'),
            'truncated_by_depth':info.get('depth') == 4 and graph.out_degree(n) == 0,
            **timing_features(linked, n),
        }
    return result
