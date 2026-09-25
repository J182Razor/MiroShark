import base64
import importlib.util
import io
import json
import zipfile
import pytest


def modules():
    assert importlib.util.find_spec('strategy_app.server'), 'The strategy web app must exist'
    from strategy_app.server import create_app, validate_input, extract_document
    from strategy_app.config import Config
    return create_app, validate_input, extract_document, Config


def call(app,path,method='GET',data=None,token='test-token-long-enough-for-workspace',origin=None):
    raw=json.dumps(data).encode() if data is not None else b''
    env={'REQUEST_METHOD':method,'PATH_INFO':path,'QUERY_STRING':'','CONTENT_LENGTH':str(len(raw)),
         'CONTENT_TYPE':'application/json','wsgi.input':io.BytesIO(raw),'wsgi.url_scheme':'http',
         'HTTP_HOST':'127.0.0.1:5100','HTTP_AUTHORIZATION':f'Bearer {token}'}
    if origin: env['HTTP_ORIGIN']=origin
    result={}
    def start(status,headers): result.update(status=int(status.split()[0]),headers=dict(headers))
    result['body']=b''.join(app(env,start))
    return result


def test_api_fails_closed_and_never_returns_provider_secrets(tmp_path):
    create,_,_,Config=modules()
    app=create(Config(token='test-token-long-enough-for-workspace',data_dir=str(tmp_path),jev_key='SECRET-JEV',frontier_key='SECRET-FRONTIER'))
    assert call(app,'/api/config',token='wrong')['status']==401
    r=call(app,'/api/config')
    assert r['status']==200
    assert b'SECRET' not in r['body']
    assert call(app,'/api/config',origin='https://hostile.example')['status']==403
    app.close()


def test_disabled_live_run_makes_no_provider_call(tmp_path):
    create,_,_,Config=modules(); app=create(Config(token='test-token-long-enough-for-workspace',data_dir=str(tmp_path)))
    r=call(app,'/api/runs','POST',{'question':'Assess a product idea','mode':'none'})
    assert r['status']==503
    app.close()


def test_missing_workspace_token_is_503(tmp_path):
    create,_,_,Config=modules(); app=create(Config(data_dir=str(tmp_path)))
    assert call(app,'/api/config')['status']==503
    app.close()


def test_input_rejects_unapproved_simulation_and_bad_threshold():
    _,validate,_,_=modules()
    with pytest.raises(ValueError): validate({'question':'A question','mode':'new'})
    with pytest.raises(ValueError): validate({'question':'A question','threshold':float('nan')})
    with pytest.raises(ValueError): validate({'question':'A question','threshold':.5})


def test_docx_extracts_tables_and_rejects_entity_xml():
    _,_,extract,_=modules()
    def doc(xml):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z: z.writestr('word/document.xml',xml)
        return base64.b64encode(out.getvalue()).decode()
    xml='<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Evidence</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'
    assert 'Table cell' in extract({'name':'evidence.docx','base64':doc(xml)})['text']
    with pytest.raises(ValueError): extract({'name':'evidence.docx','base64':doc('<!DOCTYPE a><a/>')})


def test_static_serving_is_allowlisted_and_has_csp(tmp_path):
    create,_,_,Config=modules(); app=create(Config(data_dir=str(tmp_path)))
    response=call(app,'/')
    assert response['status']==200
    assert "script-src 'self'" in response['headers']['Content-Security-Policy']
    assert call(app,'/../../.env')['status']==404
    app.close()


def test_new_simulation_enforces_existing_ask_character_contract():
    _,validate,_,_=modules()
    with pytest.raises(ValueError):validate({'question':'x'*401,'mode':'new','authorize_simulation':True})


def test_approval_does_not_get_lost_while_planner_finishes(tmp_path):
    create,_,_,Config=modules()
    from strategy_app.engine import Engine
    from strategy_app.demo import DemoClients
    app=create(Config(token='test-token-long-enough-for-workspace',data_dir=str(tmp_path)))
    payload={'question':'Demo','demo':True,'mode':'none','threshold':.95,'max_iterations':3,'evidence':[]}
    run=app.store.create(payload,'race');Engine(app.store,DemoClients()).prepare(run['id'])
    saved=app.store.get(run['id']);app.scheduler.active.add(run['id'])
    result=call(app,f"/api/runs/{run['id']}/approve",'POST',{'plan_hash':saved['plan_hash']})
    assert result['status']==429
    assert app.store.get(run['id'])['status']=='awaiting_approval'
    app.close()


def test_second_app_cannot_share_live_data_directory(tmp_path):
    create,_,_,Config=modules(); config=Config(data_dir=str(tmp_path))
    first=create(config)
    try:
        with pytest.raises(RuntimeError): create(config)
    finally: first.close()
    second=create(config);second.close()
