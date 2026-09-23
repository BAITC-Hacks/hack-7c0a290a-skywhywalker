import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.graph_engine import parse_csv, build_graph, hop_nodes, timing_features
from backend.analysis import Analysis
from backend.main import app, store
from backend import ai_copilot
from backend.models import Explanation

ROOT=Path(__file__).resolve().parents[1]
HEADER='sender,receiver,amount,timestamp\n'
def csv(rows):
    return (HEADER+rows).encode()

@pytest.fixture(scope='module')
def analysis():
    return Analysis(parse_csv((ROOT/'data/sample_transactions.csv').read_bytes()),'demo.csv')

@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    with TestClient(app) as c:
        yield c
    for k in list(store):
        if k!='demo':del store[k]

@pytest.mark.parametrize('rows',[
 'A,B,-1,2026-09-01\n','A,B,NaN,2026-09-01\n','A,B,inf,2026-09-01\n',
 'A,B,1,not-a-date\n',',B,1,2026-09-01\n'])
def test_invalid_csv(rows):
    with pytest.raises(ValueError):parse_csv(csv(rows))

def test_hops_are_bounded_and_directional():
    df=parse_csv(csv('A,B,1,2026-09-01\nB,C,1,2026-09-01\nC,D,1,2026-09-01\nD,E,1,2026-09-01\nE,F,1,2026-09-01\n'))
    g=build_graph(df)
    assert set(hop_nodes(g,'A',4,'outgoing'))==set('ABCDE')
    assert set(hop_nodes(g,'C',1,'incoming'))==set('BC')
    assert set(hop_nodes(g,'C',1,'both'))==set('BCD')

def test_fifo_does_not_double_count_or_match_past_outflows():
    df=parse_csv(csv('F,Z,100,2026-09-01T09:00:00Z\nA,F,100,2026-09-01T10:00:00Z\nF,X,80,2026-09-01T10:10:00Z\nF,Y,80,2026-09-01T10:20:00Z\n'))
    f=timing_features(df,'F')
    assert f['rapid_amount']==100
    assert sum(p['allocated_amount'] for p in f['rapid_pairs'])==100
    assert f['average_holding_minutes']==12

def test_sample_patterns_and_priority(analysis):
    assert analysis.stats['accounts']==42
    assert analysis.stats['transactions']==172
    f=analysis.nodes['F']
    assert {'COLLECTOR','CONSOLIDATOR','RAPID_PASS_THROUGH','POTENTIAL_MULE_PATTERN'}<=set(f['patterns'])
    assert f['priority_level']=='HIGH'
    assert analysis.ranking[0]['priority_score']>=analysis.ranking[-1]['priority_score']
    for n in analysis.nodes.values():
        assert 0<=n['priority_score']<=100
        assert all(0<=v<=100 for v in n['components'].values())

def test_determinism(analysis):
    other=Analysis(analysis.df,'demo.csv')
    assert other.nodes==analysis.nodes

def test_evidence_references_real_transactions(analysis):
    byid={t['id']:t for t in analysis.edges}
    for path in analysis.evidence('F')['paths']:
        assert len(path['nodes'])<=5 and 'F' in path['nodes']
        txs=[byid[i] for i in path['transaction_ids']]
        assert [(t['source'],t['target']) for t in txs]==list(zip(path['nodes'],path['nodes'][1:]))
        if path['chronological']:
            assert [t['timestamp'] for t in txs]==sorted(t['timestamp'] for t in txs)

def test_small_and_self_loop_datasets():
    a=Analysis(parse_csv(csv('A,A,100,2026-09-01\n')),'loop.csv')
    assert a.stats['total_volume']==100
    assert a.nodes['A']['features']['rapid_share']==0
    assert a.nodes['A']['components']['anomaly_score']==0


def test_api_upload_analyze_and_isolation(client):
    res=client.post('/api/upload',files={'file':('my.csv',csv('A,B,100,2026-09-01\n'),'text/csv')})
    assert res.status_code==200
    headers={'X-Dataset-ID':res.json()['dataset_id']}
    assert client.get('/api/graph',headers=headers).status_code==409
    data=client.post('/api/analyze',headers=headers).json()
    assert data['stats']['transactions']==1
    assert client.get('/api/graph').json()['stats']['transactions']==172
    assert client.get('/api/node/A',headers=headers).json()['features']['outgoing_counterparties']==1
    assert client.get('/api/network/A/hops?depth=5',headers=headers).status_code==422
    assert client.get('/api/node/F',headers=headers).status_code==404
    assert client.get('/api/graph',headers={'X-Dataset-ID':'not-found'}).status_code==404


def test_ai_fallback_all_routes(client):
    for path,body in [('/api/ai/explain-node',{'node_id':'F'}),('/api/ai/chat',{'node_id':'F','question':'Куда уходят деньги?'}),('/api/ai/compare-nodes',{'node_a':'F','node_b':'D'}),('/api/ai/investigation-summary',{})]:
        response=client.post(path,json=body)
        assert response.status_code==200,response.text
        data=response.json()
        assert data['mode']=='rules'
        assert data['limitations']
        assert data['evidence_node_ids']
    assert client.post('/api/ai/compare-nodes',json={'node_a':'F','node_b':'F'}).status_code==422


def test_ai_failure_fallback(monkeypatch,analysis):
    monkeypatch.setenv('OPENAI_API_KEY','test-key-not-real')
    def fail(**kwargs):raise RuntimeError('simulated timeout')
    monkeypatch.setattr(ai_copilot,'OpenAI',fail)
    response=ai_copilot.explain(analysis.context('F'))
    assert response['mode']=='rules'
    Explanation.model_validate(response)


def test_no_mule_from_single_factor():
    raw=HEADER+''.join(f'A{i},F,100,2026-09-01T10:00:00Z\n' for i in range(6))
    a=Analysis(parse_csv(raw.encode()),'collector.csv')
    assert 'COLLECTOR' in a.nodes['F']['patterns']
    assert 'POTENTIAL_MULE_PATTERN' not in a.nodes['F']['patterns']

def test_graph_ids_cannot_collide_with_transaction_ids():
    a=Analysis(parse_csv(csv('tx-000001,__edge__tx-000001,100,2026-09-01\n')),'ids.csv')
    payload=a.payload()
    ids=[e['data']['id'] for e in payload['nodes']+payload['edges']]
    assert len(ids)==len(set(ids))
    assert payload['edges'][0]['data']['transaction_id']=='tx-000001'


def test_chat_can_ground_explicit_comparison(client):
    response=client.post('/api/ai/chat',json={'node_id':'F','question':'Почему F выше D?'})
    assert response.status_code==200
    data=response.json()
    assert data['evidence_node_ids']==['F','D']
    assert 'D:' in data['answer']


def test_analysis_is_cached(client):
    original=store['demo']['analysis']
    client.post('/api/analyze')
    client.get('/api/node/F')
    client.get('/api/network/F/hops?depth=4')
    assert store['demo']['analysis'] is original


def test_malformed_ai_response_uses_fallback(monkeypatch,analysis):
    from types import SimpleNamespace
    monkeypatch.setenv('OPENAI_API_KEY','test-key-not-real')
    fake=SimpleNamespace(responses=SimpleNamespace(parse=lambda **kw:SimpleNamespace(output_parsed=None)))
    monkeypatch.setattr(ai_copilot,'OpenAI',lambda **kw:fake)
    assert ai_copilot.explain(analysis.context('F'))['mode']=='rules'
