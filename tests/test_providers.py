from unittest.mock import patch
import httpx
import pytest
from app.providers import Providers, ProviderError
from app.config import Settings
from app.database import Store


@pytest.fixture
def provider(tmp_path):
    config=Settings(data_dir=tmp_path,database_url=f'sqlite:///{tmp_path}/db.sqlite3',provider='gemini',
                    model='test-model',gemini_api_key='fake-key',_env_file=None)
    return Providers(config,Store(config))


def model_response(value):
    import json
    return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(value)}]}}]},
                          request=httpx.Request('POST','https://generativelanguage.googleapis.com'))


def test_live_plan_contract(provider):
    with patch('httpx.post',return_value=model_response({'subquestions':['What is supported?'],
                                                       'search_queries':['supporting research evidence']})) as post:
        plan=provider.plan('What is supported by evidence?')
        assert len(plan.subquestions)==1
        assert post.call_args.kwargs['headers']['x-goog-api-key']=='fake-key'
        assert post.call_args.kwargs['json']['generationConfig']['maxOutputTokens']==2048


def test_cited_summary_contract(provider):
    evidence=[{'id':'E001','quote':'A sufficiently long statement from a source.'}]
    with patch('httpx.post',return_value=model_response({'summary':'The source makes this statement. [E001]'})):
        assert '[E001]' in provider.summarize('Question',evidence)


@pytest.mark.parametrize('summary',['Unsupported claim.','Invalid citation. [E999]'])
def test_invalid_summary_rejected(provider,summary):
    with patch('httpx.post',return_value=model_response({'summary':summary})):
        with pytest.raises(ProviderError):
            provider.summarize('Question',[{'id':'E001','quote':'Source statement.'}])


def test_search_contract(provider):
    provider.settings.brave_api_key='fake-search-key'
    response=httpx.Response(200,json={'web':{'results':[{'url':'https://example.org','title':'Example'}]}},
                            request=httpx.Request('GET','https://api.search.brave.com'))
    with patch('httpx.get',return_value=response) as get:
        result=provider.search('test query')
    assert result[0]['url']=='https://example.org'
    assert get.call_args.kwargs['params']['count']==5


def test_provider_failure_redacted(provider):
    response=httpx.Response(403,request=httpx.Request('POST','https://generativelanguage.googleapis.com'))
    with patch('httpx.post',return_value=response):
        with pytest.raises(ProviderError) as error:
            provider.plan('Question?')
    assert 'fake-key' not in str(error.value)
