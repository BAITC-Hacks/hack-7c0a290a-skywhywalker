import networkx as nx
from .graph_engine import timing_features

def calculate_features(df, graph):
    undirected = graph.to_undirected()
    groups = sorted(nx.community.louvain_communities(undirected, weight='weight', seed=42), key=lambda g: min(g))
    community = {n:i+1 for i,g in enumerate(groups) for n in g}
    centrality = nx.degree_centrality(graph)
    between = nx.betweenness_centrality(graph, k=min(100,len(graph)) if len(graph)>250 else None, seed=42)
    pagerank = nx.pagerank(graph, weight='weight', max_iter=1000)
    result = {}
    for n in sorted(graph):
        inc = df[df.receiver == n]
        out = df[df.sender == n]
        linked = df[(df.sender == n) | (df.receiver == n)]
        incoming, outgoing = float(inc.amount.sum()), float(out.amount.sum())
        neighbors = (set(graph.predecessors(n)) | set(graph.successors(n))) - {n}
        result[n] = {
            'incoming_transaction_count':len(inc), 'outgoing_transaction_count':len(out),
            'transaction_count':len(linked),
            'incoming_counterparties':len(set(inc.sender)-{n}), 'outgoing_counterparties':len(set(out.receiver)-{n}),
            'total_incoming_amount':incoming, 'total_outgoing_amount':outgoing,
            'total_volume':float(linked.amount.sum()), 'in_out_ratio':incoming/outgoing if outgoing else None,
            'turnover_ratio':min(incoming,outgoing)/max(incoming,outgoing) if max(incoming,outgoing) else 0,
            'degree_centrality':centrality[n], 'in_degree':graph.in_degree(n), 'out_degree':graph.out_degree(n),
            'betweenness':between[n], 'pagerank':pagerank[n], 'community_id':community[n],
            'average_incoming_amount':float(inc.amount.mean()) if len(inc) else 0,
            'average_outgoing_amount':float(out.amount.mean()) if len(out) else 0,
            'median_amount':float(linked.amount.median()),
            'communities_connected':len({community[v] for v in neighbors}),
            **timing_features(df,n)
        }
    return result
