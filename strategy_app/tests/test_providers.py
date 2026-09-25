import importlib.util
import pytest


def providers():
    assert importlib.util.find_spec('strategy_app.providers'), 'Provider adapters must exist'
    from strategy_app import providers as module
    return module


class Wire:
    def __init__(self, reply): self.reply, self.calls = reply, []
    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs)); return self.reply


def test_jev_native_contract_and_noul_field():
    p = providers()
    wire = Wire({'model':'jev-1.13.0','answers':{'Q':{'type':'noul','noul':.98}},'usage':{}})
    result = p.JevClient('secret', 'jev-1.13.0', wire).decide({'evidence': []}, {'Q': {'type':'noul','instructions':'Check Q'}})
    assert result['answers']['Q']['noul'] == .98
    args, kwargs = wire.calls[0]
    assert args[1] == 'https://api.typesafe.ai/v1/systemone'
    assert kwargs['body']['model'] == 'jev-1.13.0'
    assert kwargs['headers']['Authorization'] == 'Bearer secret'


def test_jev_wrong_model_is_not_silently_accepted():
    p = providers()
    wire = Wire({'model':'different','answers':{'Q':{'type':'noul','noul':.98}}})
    with pytest.raises(p.ProviderError): p.JevClient('s', 'jev-1.13.0', wire).decide({}, {'Q': {'type':'noul','instructions':'x'}})


@pytest.mark.parametrize('url', ['http://example.com/v1','https://user:pass@example.com','file:///etc/passwd','https://example.com/?key=secret'])
def test_reject_unsafe_configured_provider_urls(url):
    with pytest.raises(ValueError): providers().validate_base_url(url)


def test_accept_local_selfhosted_endpoint():
    assert providers().validate_base_url('http://127.0.0.1:5001/') == 'http://127.0.0.1:5001'


def test_llm_returns_structured_json():
    p = providers(); wire = Wire({'choices':[{'message':{'content':'{"summary":"ok"}'}}], 'usage':{}})
    assert p.LLMClient('https://example.com/v1', 'key', 'configured-model', wire).generate('policy', {'question':'q'})['summary'] == 'ok'


def test_existing_simulation_must_be_completed():
    p = providers(); wire = Wire({'success':True,'data':{'runner_status':'running'}})
    with pytest.raises(p.ProviderError): p.MiroSharkClient('http://localhost:5001','key',wire).existing('sim_abc', lambda *args: None)


def test_existing_simulation_reads_real_actions():
    p = providers()
    class Responses(Wire):
        def request(self, method, url, **kwargs):
            self.calls.append(url)
            if url.endswith('/run-status'): return {'success':True,'data':{'runner_status':'completed'}}
            return {'success':True,'data':{'actions':[{'action_type':'like'}]}}
    wire=Responses(None)
    result=p.MiroSharkClient('http://localhost:5001','key',wire).existing('sim_abc',lambda *args:None)
    assert result['kind']=='simulation_observation'
    assert any('/actions?' in url for url in wire.calls)


def test_jev_choice_must_return_known_option():
    p = providers()
    wire=Wire({'model':'jev-1.13.0','answers':{'Q':{'type':'choice','choice':'FAKE','probabilities':{'unknown':1},'confidence':1}}})
    with pytest.raises(p.ProviderError):
        p.JevClient('s','jev-1.13.0',wire).decide({}, {'Q':{'type':'choice','instructions':'x','criteria':{'yes':'Y','unknown':'Unknown'}}})


def test_new_simulation_uses_actual_api_sequence_and_no_post_retries():
    p=providers()
    class Sequence(Wire):
        def request(self,method,url,**kwargs):
            self.calls.append((method,url,kwargs))
            path=url.split('5001',1)[1]
            values={
                '/api/simulation/ask':{'simulation_requirement':'Explore the strategic question','seed_document':'Hypothetical seed'},
                '/api/graph/ontology/generate':{'project_id':'proj_test'},
                '/api/graph/build':{'task_id':'task_test'},
                '/api/graph/task/task_test':{'status':'completed'},
                '/api/simulation/create':{'simulation_id':'sim_test'},
                '/api/simulation/prepare':{'status':'preparing'},
                '/api/simulation/sim_test':{'status':'ready'},
                '/api/simulation/start':{'runner_status':'starting'},
                '/api/simulation/sim_test/run-status':{'runner_status':'completed'},
                '/api/simulation/sim_test/actions?limit=100&offset=0':{'actions':[{'action_type':'create_comment'}]}}
            return {'success':True,'data':values[path]}
    wire=Sequence(None); events=[]
    source=p.MiroSharkClient('http://localhost:5001','internal',wire,sleep=lambda _:None).new('Test strategic question',[],6,lambda k,d:events.append((k,d)))
    assert source['simulation_id']=='sim_test'
    assert len(wire.calls)==11
    for method,url,kwargs in wire.calls:
        if method=='POST': assert kwargs['safe'] is False
        assert kwargs['headers']['x-miroshark-internal-key']=='internal'
    assert any(k=='project_created' for k,d in events)
    assert any(k=='simulation_created' for k,d in events)


def test_network_failure_on_mutation_is_not_retried_and_is_redacted():
    p=providers()
    from urllib.error import URLError
    class Broken:
        calls=0
        def open(self,*args,**kwargs):
            self.calls+=1;raise URLError('SECRET-DO-NOT-LOG')
    broken=Broken()
    with pytest.raises(p.ProviderError) as exc:
        p.HTTPTransport(opener=broken).request('POST','http://localhost:5001/api/simulation/create',body={})
    assert broken.calls==1 and 'SECRET' not in str(exc.value)
    assert 'not retried' in str(exc.value)
