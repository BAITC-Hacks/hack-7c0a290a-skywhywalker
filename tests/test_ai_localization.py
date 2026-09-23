from types import SimpleNamespace
import httpx
import pytest
from openai import AuthenticationError, PermissionDeniedError, RateLimitError, APIConnectionError
from backend import ai_copilot as ai
from backend.models import Explanation

NODE={'node_id':'F','priority_score':82,'priority_level':'HIGH','components':{'graph_score':80,'anomaly_score':90,'pattern_score':75,'flow_score':80},'features':{'incoming_counterparties':6,'outgoing_counterparties':3}}

def test_fallback_uses_plain_russian(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','')
    result=ai.explain({'node':NODE})
    assert result['mode']=='rules' and result['reason']=='not_configured'
    assert 'Счёт F' in result['summary'] and 'HIGH' not in result['summary']
    assert all('_score' not in s['name'] for s in result['signals'])

def test_openai_response_keeps_calculated_evidence(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    captured={}
    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_parsed=Explanation(summary='Счёт выделен',priority_explanation='По данным',signals=[{'name':'Выдумано','evidence':'999'}],suggested_checks=['Проверить'],limitations='Ограничения'))
    monkeypatch.setattr(ai,'OpenAI',lambda **kwargs:SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    result=ai.explain({'node':NODE})
    assert result['mode']=='openai'
    assert '999' not in str(result['signals'])
    assert captured['store'] is False
    assert 'test-only' not in captured['input']

@pytest.mark.parametrize('status,exception,reason',[(401,AuthenticationError,'invalid_key'),(403,PermissionDeniedError,'access_denied'),(429,RateLimitError,'rate_limit')])
def test_api_error_does_not_expose_raw_exception(monkeypatch,status,exception,reason):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    response=httpx.Response(status,request=httpx.Request('POST','https://api.openai.com/v1/responses'))
    def fail(**kwargs):raise exception('PRIVATE-ERROR-CONTENT',response=response,body=None)
    monkeypatch.setattr(ai,'OpenAI',fail)
    result=ai.explain({'node':NODE})
    assert result['mode']=='rules' and result['reason']==reason
    assert 'PRIVATE-ERROR-CONTENT' not in str(result)
