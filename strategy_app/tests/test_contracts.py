import importlib.util
from copy import deepcopy
import math
import pytest


def contracts():
    assert importlib.util.find_spec('strategy_app.contracts'), 'Strategy contracts must exist'
    from strategy_app import contracts as module
    return module


def plan():
    return {'outcome_contract': {'desired_outcome': 'Choose a reversible test',
      'success_observable': 'A decision memo with alternatives', 'constraints': ['No spending'],
      'prohibited_actions': ['external side effects'], 'actor_or_owner':'User','environment':'Test',
      'failure_observable':'Unsupported decision','deadline_or_sla':'Not specified',
      'required_evidence':[],'reversible_actions':['Create analysis'],'irreversible_actions':[],
      'human_approval_boundaries':['Approve plan']},
      'assumptions': ['Demand is unknown'], 'questions': ['Which customer?'],
      'atoms': [{'id': 'A1', 'objective': 'Identify missing evidence', 'action': 'List gaps',
      'object': 'Supplied context', 'executor': 'lower_tier', 'dependencies': [],
      'postcondition': 'Each gap names a verification step', 'failure_path': 'human_review',
      'evidence_ids': ['E1'], 'side_effect': 'none'}]}


def test_contract_accepts_valid_graph():
    assert contracts().validate_plan(plan(), {'E1'}) == ['A1']


@pytest.mark.parametrize('change', ['cycle', 'unknown_evidence', 'side_effect', 'duplicate', 'unknown_executor'])
def test_contract_rejects_invalid_graph(change):
    p = plan()
    if change == 'cycle': p['atoms'][0]['dependencies'] = ['A1']
    if change == 'unknown_evidence': p['atoms'][0]['evidence_ids'] = ['FAKE']
    if change == 'side_effect': p['atoms'][0]['side_effect'] = 'irreversible'
    if change == 'duplicate': p['atoms'].append(deepcopy(p['atoms'][0]))
    if change == 'unknown_executor': p['atoms'][0]['executor'] = 'shell'
    with pytest.raises(ValueError): contracts().validate_plan(p, {'E1'})


def test_weakest_critical_validator_gates_not_average():
    c = contracts()
    values = {name: .999 for name in c.PLAN_CHECKS}
    values['state_sufficiency'] = .80
    result = c.gate(values, .95)
    assert not result['passed']
    assert result['acceptance_score'] == .80
    assert result['calibration_status'] == 'unvalidated'
    assert result['reliability_probability'] is None


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -.1, 1.1, True, '0.99'])
def test_gate_rejects_invalid_probabilities(value):
    with pytest.raises(ValueError): contracts().gate({'a': value}, .95)


def test_missing_critical_answer_fails_closed():
    c = contracts()
    with pytest.raises(ValueError): c.parse_nouls({'answers': {}}, ['A1_atomicity'])


def test_repair_cannot_change_outcome_or_accepted_atom():
    c = contracts()
    old = plan(); new = deepcopy(old)
    new['outcome_contract']['desired_outcome'] = 'Send offers'
    with pytest.raises(ValueError): c.validate_repair(old, new, set())
    new = deepcopy(old); new['atoms'][0]['action'] = 'Change action'
    with pytest.raises(ValueError): c.validate_repair(old, new, set())


def test_repair_can_change_failed_atom_only():
    c = contracts(); old = plan(); new = deepcopy(old)
    new['atoms'][0]['action'] = 'List evidence gaps by source'
    c.validate_repair(old, new, {'A1'})


def test_outcome_and_validation_score_not_success_forecast():
    c = contracts()
    result = c.gate({'a': .98, 'b': .99}, .95)
    assert result['passed'] and result['reliability_probability'] is None


def test_source_category_cannot_be_laundered():
    c=contracts()
    value={'summary':'Result','assumptions':[],'evidence_gaps':[],
           'claims':[{'statement':'Real customer purchased','kind':'user_supplied','evidence_ids':['E_SIM']}]}
    with pytest.raises(ValueError): c.validate_result(value,{'E_SIM'},source_kinds={'E_SIM':'simulation_observation'})


def test_contract_requires_observable_failure_rule():
    p=plan();p['outcome_contract'].pop('failure_observable',None)
    with pytest.raises(ValueError): contracts().validate_plan(p,{'E1'})
