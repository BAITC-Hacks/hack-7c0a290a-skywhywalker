WEIGHTS = {'graph_score':.35,'anomaly_score':.25,'pattern_score':.25,'flow_score':.15}

def calculate_priorities(features, anomalies, patterns):
    maxima = {k:max(f[k] for f in features.values()) for k in ['betweenness','pagerank','degree_centrality']}
    results = {}
    for n,f in features.items():
        graph_score = sum(w * f[k]/maxima[k] * 100 if maxima[k] else 0 for k,w in [('betweenness',.5),('pagerank',.25),('degree_centrality',.25)])
        p = patterns[n]['patterns']
        # FAN_IN / FAN_OUT aliases are not counted twice.
        pattern_score = min(100, sum({'COLLECTOR':20,'DISTRIBUTOR':20,'CONSOLIDATOR':25,'BRIDGE':25,'RAPID_PASS_THROUGH':25,'POTENTIAL_MULE_PATTERN':25}.get(x,0) for x in p))
        flow_score = 100*(.7*f['rapid_share'] + .3*f['turnover_ratio'])
        parts = {'graph_score':round(graph_score,2),'anomaly_score':round(anomalies[n],2),'pattern_score':pattern_score,'flow_score':round(flow_score,2)}
        score = round(sum(parts[k]*w for k,w in WEIGHTS.items()),2)
        results[n] = {'node_id':n,'priority_score':score,'priority_level':'HIGH' if score>=70 else 'MEDIUM' if score>=40 else 'LOW','components':parts,'features':f,**patterns[n]}
    return results
