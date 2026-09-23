WEIGHTS = {'graph_score':.35,'anomaly_score':.25,'pattern_score':.25,'flow_score':.15}


def calculate_priorities(features, anomalies, patterns):
    maxima = {k:max((f.get(k,0) for f in features.values()), default=0)
              for k in ['betweenness','pagerank','degree_centrality','seed_reach']}
    graph_weights = [('betweenness',.4),('pagerank',.2),('degree_centrality',.2),('seed_reach',.2)] if maxima['seed_reach'] else [('betweenness',.5),('pagerank',.25),('degree_centrality',.25)]
    results = {}
    for n, f in features.items():
        graph_score = sum(w*f.get(k,0)/maxima[k]*100 if maxima[k] else 0 for k,w in graph_weights)
        p = patterns[n]['patterns']
        pattern_score = min(100, sum({'COLLECTOR':20,'DISTRIBUTOR':20,'CONSOLIDATOR':25,'BRIDGE':25,'RAPID_PASS_THROUGH':25,'POTENTIAL_MULE_PATTERN':25}.get(x,0) for x in p))
        flow_available = bool(f.get('timing_available',True) and not f.get('is_seed') and not f.get('truncated_by_depth'))
        flow_score = 100*(.7*(f.get('rapid_share') or 0)+.3*f['turnover_ratio']) if flow_available else 0
        availability = {k:k!='flow_score' or flow_available for k in WEIGHTS}
        weight_total = sum(v for k,v in WEIGHTS.items() if availability[k])
        weights = {k:v/weight_total if availability[k] else 0 for k,v in WEIGHTS.items()}
        parts = {'graph_score':round(graph_score,2),'anomaly_score':round(anomalies[n],2),'pattern_score':pattern_score,'flow_score':round(flow_score,2)}
        multiplier = (.7 if f.get('is_seed') else 1)*(.65 if f.get('truncated_by_depth') else 1)
        score = round(sum(parts[k]*weights[k] for k in parts)*multiplier,2)
        results[n] = {'node_id':n,'priority_score':score,
            'priority_level':'HIGH' if score>=70 else 'MEDIUM' if score>=40 else 'LOW',
            'components':parts,'component_availability':availability,'score_weights':weights,
            'priority_multiplier':multiplier,'features':f,**patterns[n]}
    return results
