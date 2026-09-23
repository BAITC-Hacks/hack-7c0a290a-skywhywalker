import io
import re
from collections import deque
import networkx as nx
import numpy as np
import pandas as pd

MAX_ROWS = 20000
MAX_NODES = 1500

def parse_csv(raw: bytes) -> pd.DataFrame:
    try:
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
    except Exception as exc:
        raise ValueError('Не удалось прочитать CSV в UTF-8.') from exc
    required = ['sender', 'receiver', 'amount', 'timestamp']
    if not set(required).issubset(df.columns):
        raise ValueError('Обязательные столбцы: sender,receiver,amount,timestamp')
    df = df[required].copy()
    if not 1 <= len(df) <= MAX_ROWS:
        raise ValueError(f'Допустимо от 1 до {MAX_ROWS} транзакций.')
    for col in ['sender', 'receiver']:
        df[col] = df[col].str.strip()
        if not df[col].map(lambda v: bool(re.fullmatch(r'[\w.\-:@ ]{1,64}', v))).all():
            raise ValueError('Идентификатор счёта: 1–64 букв, цифр, пробелов или символов . - : @ _')
    df['amount'] = pd.to_numeric(df.amount, errors='coerce')
    if not (np.isfinite(df.amount) & (df.amount > 0) & (df.amount <= 1e15)).all():
        raise ValueError('Суммы должны быть конечными положительными числами не более 10^15.')
    df['timestamp'] = pd.to_datetime(df.timestamp, errors='coerce', utc=True, format='mixed')
    if df.timestamp.isna().any():
        raise ValueError('Некорректное время перевода (timestamp). Используйте ISO 8601. Время без зоны считается UTC.')
    if len(set(df.sender) | set(df.receiver)) > MAX_NODES:
        raise ValueError(f'Для MVP разрешено не более {MAX_NODES} узлов.')
    df['id'] = [f'tx-{i+1:06d}' for i in range(len(df))]
    return df.sort_values(['timestamp','id'], kind='stable').reset_index(drop=True)

def build_graph(df):
    graph = nx.DiGraph()
    for row in df.itertuples():
        if graph.has_edge(row.sender, row.receiver):
            graph[row.sender][row.receiver]['weight'] += float(row.amount)
            graph[row.sender][row.receiver]['count'] += 1
        else:
            graph.add_edge(row.sender, row.receiver, weight=float(row.amount), count=1)
    return graph

def transactions(df):
    return [{'id':r.id, 'source':r.sender, 'target':r.receiver, 'amount':float(r.amount),
             'timestamp':r.timestamp.isoformat()} for r in df.itertuples()]

def hop_nodes(graph, node, depth, direction='both'):
    traversal = graph.to_undirected() if direction == 'both' else graph if direction == 'outgoing' else graph.reverse(copy=False)
    return nx.single_source_shortest_path_length(traversal, node, cutoff=depth)

def timing_features(df, node):
    # FIFO allocation is a heuristic, not identification of the same money.
    incoming = deque()
    matched = rapid = weighted_minutes = 0.0
    pairs = []
    for row in df[(df.sender == node) | (df.receiver == node)].itertuples():
        if row.sender == row.receiver:
            continue
        if row.receiver == node:
            incoming.append([float(row.amount), row.timestamp, row.id])
        else:
            remaining = float(row.amount)
            while remaining > 1e-8 and incoming:
                lot = incoming[0]
                amount = min(remaining, lot[0])
                minutes = (row.timestamp - lot[1]).total_seconds() / 60
                matched += amount
                weighted_minutes += minutes * amount
                if 0 <= minutes <= 60:
                    rapid += amount
                    if len(pairs) < 20:
                        pairs.append({'incoming_transaction':lot[2], 'outgoing_transaction':row.id,
                                      'allocated_amount':round(amount,2), 'minutes':round(minutes,2)})
                remaining -= amount
                lot[0] -= amount
                if lot[0] <= 1e-8:
                    incoming.popleft()
    total_in = float(df[(df.receiver == node) & (df.sender != node)].amount.sum())
    return {'matched_amount':matched, 'rapid_amount':rapid,
            'rapid_share':rapid / total_in if total_in else 0,
            'average_holding_minutes': weighted_minutes / matched if matched else None,
            'rapid_pairs':pairs}
