import importlib.util
import pytest


def modules():
    assert importlib.util.find_spec('strategy_app.engine'), 'Durable orchestration must exist'
    from strategy_app.engine import Engine, RunStopped
    from strategy_app.store import Store
    from strategy_app.demo import DemoClients, DEMO_QUESTION
    return Engine, RunStopped, Store, DemoClients, DEMO_QUESTION


def request_payload(question):
    return {'question':question, 'context':'Illustrative demo only', 'constraints':'No external actions',
            'mode':'none', 'demo':True, 'threshold':.95, 'max_iterations':3, 'rounds':6, 'evidence':[]}


def test_demo_runs_real_orchestration_and_requires_approval(tmp_path):
    Engine, _, Store, Clients, question = modules()
    store=Store(tmp_path/'runs.sqlite3')
    run=store.create(request_payload(question), 'one')
    engine=Engine(store, Clients())
    engine.prepare(run['id'])
    prepared=store.get(run['id'])
    assert prepared['status']=='awaiting_approval'
    assert 'report' not in prepared
    store.approve(run['id'], prepared['plan_hash'])
    engine.execute(run['id'])
    done=store.get(run['id'])
    assert done['status']=='completed'
    assert done['demo'] is True
    assert len(done['report']['options'])>=2
    assert done['final_gate']['reliability_probability'] is None
    assert set(done['report']['swotmm'])=={'strengths','weaknesses','opportunities','threats','moats','monetization'}


def test_idempotency_reuses_same_payload_but_rejects_different(tmp_path):
    _, _, Store, _, question = modules()
    store=Store(tmp_path/'runs.sqlite3'); data=request_payload(question)
    a=store.create(data,'same'); b=store.create(data,'same')
    assert a['id']==b['id']
    with pytest.raises(ValueError): store.create({**data,'question':'Different'},'same')


def test_cancel_prevents_any_provider_calls(tmp_path):
    Engine, _, Store, Clients, question=modules()
    store=Store(tmp_path/'runs.sqlite3'); run=store.create(request_payload(question),'cancel')
    store.cancel(run['id']); engine=Engine(store,Clients()); engine.prepare(run['id'])
    assert store.get(run['id'])['status']=='cancelled'


def test_low_gate_never_lowers_threshold_or_executes(tmp_path):
    Engine, _, Store, Clients, question=modules()
    clients=Clients(); clients.jev.score=.7
    store=Store(tmp_path/'runs.sqlite3'); run=store.create(request_payload(question),'low')
    Engine(store,clients).prepare(run['id'])
    saved=store.get(run['id'])
    assert saved['status']=='needs_review'
    assert len(saved['revisions'])==3
    assert saved['input']['threshold']==.95
    assert not saved.get('outputs')


def test_approval_rejects_wrong_hash_and_duplicate(tmp_path):
    Engine, _, Store, Clients, question=modules()
    store=Store(tmp_path/'runs.sqlite3'); run=store.create(request_payload(question),'hash')
    Engine(store,Clients()).prepare(run['id'])
    prepared=store.get(run['id'])
    with pytest.raises(ValueError): store.approve(run['id'],'bad')
    store.approve(run['id'],prepared['plan_hash'])
    with pytest.raises(ValueError): store.approve(run['id'],prepared['plan_hash'])


def test_restart_marks_in_flight_interrupted_not_completed(tmp_path):
    _, _, Store, _, question=modules()
    db=tmp_path/'runs.sqlite3'; store=Store(db)
    run=store.create(request_payload(question),'restart')
    store.update(run['id'], status='executing')
    Store(db).recover_interrupted()
    assert store.get(run['id'])['status']=='interrupted'


def test_execute_without_approval_is_rejected(tmp_path):
    Engine, _, Store, Clients, question=modules()
    store=Store(tmp_path/'runs.sqlite3'); run=store.create(request_payload(question),'unapproved')
    engine=Engine(store,Clients()); engine.prepare(run['id']); engine.execute(run['id'])
    assert store.get(run['id'])['status']=='needs_review'


def test_late_remote_identifier_survives_cancellation(tmp_path):
    Engine, _, Store, Clients, question=modules()
    store=Store(tmp_path/'runs.sqlite3'); run=store.create(request_payload(question),'late-id')
    engine=Engine(store,Clients()); engine.begin(run['id']); store.cancel(run['id'])
    engine.emit('simulation_created',{'simulation_id':'sim_created_before_cancel'})
    saved=store.get(run['id'])
    assert saved['simulation_id']=='sim_created_before_cancel' and saved['status']=='cancelled'
