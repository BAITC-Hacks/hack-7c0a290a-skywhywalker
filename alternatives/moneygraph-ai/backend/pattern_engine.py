def detect_patterns(features, graph):
    results = {}
    for n, f in features.items():
        patterns = []
        rules = []
        def add(name, observed, rule):
            patterns.append(name)
            rules.append({'pattern':name,'observed':observed,'rule':rule})
        if f['incoming_counterparties'] >= 5:
            add('COLLECTOR',f['incoming_counterparties'],'unique incoming counterparties >= 5')
            add('FAN_IN',f['incoming_counterparties'],'unique incoming counterparties >= 5')
        if f['outgoing_counterparties'] >= 5:
            add('DISTRIBUTOR',f['outgoing_counterparties'],'unique outgoing counterparties >= 5')
            add('FAN_OUT',f['outgoing_counterparties'],'unique outgoing counterparties >= 5')
        branches = [v for v in graph.predecessors(n) if v != n and features[v]['incoming_counterparties'] >= 2]
        if len(branches) >= 2:
            add('CONSOLIDATOR',branches,'at least 2 incoming branches each have >= 2 sources')
        if f['communities_connected'] >= 2 and f['betweenness'] >= .02:
            add('BRIDGE',{'communities':f['communities_connected'],'betweenness':f['betweenness']},'communities >= 2 AND betweenness >= 0.02')
        if f['rapid_share'] >= .6 and f['turnover_ratio'] >= .7:
            add('RAPID_PASS_THROUGH',{'rapid_share':f['rapid_share'],'turnover':f['turnover_ratio']},'FIFO incoming volume forwarded within 60 minutes >= 60% AND turnover >= 70%')
        mule = {'multiple_sources':f['incoming_counterparties'] >= 5,
                'rapid_forwarding':f['rapid_share'] >= .6,
                'high_turnover':f['turnover_ratio'] >= .8,
                'fan_in_fan_out':f['outgoing_counterparties'] >= 3 and f['incoming_counterparties'] >= 5}
        if all(mule.values()):
            add('POTENTIAL_MULE_PATTERN',mule,'all four conditions must hold; sources are distinct accounts, independence is not established')
        results[n] = {'patterns':patterns,'pattern_evidence':rules,'mule_signal_count':sum(mule.values())}
    return results
