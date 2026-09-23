import numpy as np
from sklearn.ensemble import IsolationForest

def anomaly_scores(features):
    keys = list(features)
    fields = ['transaction_count','total_volume','incoming_counterparties','outgoing_counterparties','turnover_ratio','betweenness','pagerank']
    values = np.array([[features[n][f] for f in fields] for n in keys], dtype=float)
    values = np.log1p(values)
    if len(keys) < 5 or np.all(values == values[0]):
        return {n:0.0 for n in keys}
    model = IsolationForest(n_estimators=150, random_state=42, contamination='auto', n_jobs=1)
    model.fit(values)
    raw = -model.score_samples(values)
    # Dataset-relative normalization; not a fraud probability.
    span = float(np.ptp(raw))
    return {n:float((s-raw.min())/span*100) if span else 0.0 for n,s in zip(keys,raw)}
