import io
from collections import Counter
import networkx as nx
from .graph_engine import build_graph, transactions, hop_nodes
from .feature_engine import calculate_features
from .pattern_engine import detect_patterns
from .anomaly_engine import anomaly_scores
from .risk_engine import calculate_priorities, WEIGHTS
from .roles_engine import assign_roles

class Analysis:
    def __init__(self, df, filename):
        self.df = df
        self.filename = filename
        self.graph = build_graph(df)
        features = calculate_features(df,self.graph)
        roles = assign_roles(features,self.graph,df)
        for n,role in roles.items():
            features[n].update({k:v for k,v in role.items() if k not in {'role','role_score','role_evidence'}})
        self.nodes = calculate_priorities(features,anomaly_scores(features),detect_patterns(features,self.graph))
        for n,role in roles.items():
            self.nodes[n].update(role)
        self.metadata = {k:df.attrs.get(k) for k in ['time_precision','currency','source_kind','warnings']}
        self.metadata['warnings'] = self.metadata['warnings'] or []
        self.ranking = sorted(self.nodes.values(),key=lambda n:(-n['priority_score'],n['node_id']))
        self.edges = transactions(df)
        self.edge_prefix = '__edge__'
        while any(n.startswith(self.edge_prefix) for n in self.nodes):
            self.edge_prefix += '_' 
        self.by_pair = {}
        for tx in self.edges:
            self.by_pair.setdefault((tx['source'],tx['target']),[]).append(tx)
        self.pattern_counts = dict(Counter(p for n in self.nodes.values() for p in n['patterns']))
        self.stats = {'accounts':len(self.nodes),'transactions':len(df),'links':self.graph.number_of_edges(),
            'total_volume':float(df.amount.sum()),'communities':len({f['community_id'] for f in features.values()}),
            'high_priority':sum(n['priority_level']=='HIGH' for n in self.nodes.values()),
            'detected_patterns':sum(self.pattern_counts.values()),'filename':filename,
            'start':df.timestamp.min().isoformat(),'end':df.timestamp.max().isoformat(),
            'seed_count':sum(n['is_seed'] for n in self.nodes.values()),
            'isolated_count':len(list(nx.isolates(self.graph))),
            'boundary_count':sum(n['truncated_by_depth'] for n in self.nodes.values()),
            'weak_components':nx.number_weakly_connected_components(self.graph),**self.metadata}

    def payload(self, ids=None):
        ids = set(self.nodes) if ids is None else set(ids)
        return {'nodes':[{'data':{'id':n,'label':n,'priority_score':v['priority_score'],
            'priority_level':v['priority_level'],'patterns':v['patterns'],'community_id':v['features']['community_id'],
            'role':v['role'],'is_seed':v['is_seed'],'depth':v['depth'],'truncated_by_depth':v['truncated_by_depth'],
            'volume':v['features']['total_volume']}} for n,v in self.nodes.items() if n in ids],
            'edges':[{'data':{**t, 'id':self.edge_prefix+t['id'], 'transaction_id':t['id']}} for t in self.edges if t['source'] in ids and t['target'] in ids], 'stats':self.stats}

    def paths(self,node,limit=8):
        # A bounded sample of real directed paths containing the selected node, <=4 edges.
        upstream = list(nx.single_source_shortest_path(self.graph.reverse(copy=False),node,cutoff=2).values())
        downstream = list(nx.single_source_shortest_path(self.graph,node,cutoff=2).values())
        upstream.sort(key=lambda p:(-len(p),p))
        downstream.sort(key=lambda p:(-len(p),p))
        result = []
        for u in upstream[:30]:
            for d in downstream[:30]:
                path = list(reversed(u)) + d[1:]
                if len(path)<2 or len(set(path))!=len(path):
                    continue
                chosen = []
                last = ''
                ordered = True
                for a,b in zip(path,path[1:]):
                    tx = next((t for t in self.by_pair[(a,b)] if (t['timestamp'][:10]>last[:10] if self.metadata['time_precision']=='day' else t['timestamp']>=last)),None)
                    if tx is None:
                        ordered = False
                        break
                    chosen.append(tx['id'])
                    last = tx['timestamp']
                result.append({'nodes':path,'chronological':ordered,'time_precision':self.metadata['time_precision'],
                    'transaction_ids':chosen if ordered else [self.by_pair[(a,b)][0]['id'] for a,b in zip(path,path[1:])],
                    'interpretation':'time-ordered structural path; same-funds attribution not established' if ordered else 'structural path only; no time-ordered sequence found'})
                if len(result)>=limit:
                    return result
        return result

    def evidence(self,node):
        txs = [t for t in self.edges if node in (t['source'],t['target'])]
        return {'node_id':node,'metrics':self.nodes[node]['features'],
            'components':self.nodes[node]['components'],'score_weights':self.nodes[node]['score_weights'],
            'component_availability':self.nodes[node]['component_availability'],
            'priority_multiplier':self.nodes[node]['priority_multiplier'],'metadata':self.metadata,
            'rules':self.nodes[node]['pattern_evidence'],'paths':self.paths(node),
            'transactions':txs[:500],'transaction_count':len(txs),'transactions_truncated':len(txs)>500,
            'methodology':'Направленное посредничество; PageRank по объёмам; Louvain на проекции с суммой log1p весов; Isolation Forest, seed=42. Минутный FIFO доступен только при точном времени; для дат не рассчитывается. Роли и приоритеты — гипотезы, не вероятности.'}

    def context(self,node):
        ev = self.evidence(node)
        return {'node':self.nodes[node],'paths':ev['paths'],'metadata':self.metadata,
            'transactions':ev['transactions'][:25], 'transaction_sample_limit':25,
            'outgoing_counterparties':sorted([{'node_id':v,'amount':self.graph[node][v]['weight']} for v in self.graph.successors(node)],key=lambda x:-x['amount'])[:10],
            'rules':ev['rules']}
