"""Deterministic contracts. Model agreement is never a reliability guarantee."""
from __future__ import annotations

import hashlib
import json
import math
import re
from graphlib import TopologicalSorter, CycleError

SCHEMA_VERSION = 'strategy-1'
ATOM_ID = re.compile(r'^[A-Z][A-Z0-9_-]{0,39}$')
SWOTMM = ('strengths', 'weaknesses', 'opportunities', 'threats', 'moats', 'monetization')
PLAN_CHECKS = {
    'outcome_fidelity': 'Successful completion materially advances the unchanged user question and outcome.',
    'atomicity': 'There is one independently executable judgment or analysis operation, not several hidden tasks.',
    'action_clarity': 'The action, object and starting inputs are unambiguous.',
    'state_sufficiency': 'Named evidence or predecessor outputs suffice for this operation. Unknowns must remain unknown; hypothetical reasoning must be labeled.',
    'answer_space': 'A Jev choice includes an unknown escape and distinct meaningful options. For a generative or code node, the output contract is explicit.',
    'dependency_correctness': 'Required predecessor tasks are declared and their outputs are appropriate.',
    'observability': 'The postcondition gives an observable way to check the output.',
    'executor_fit': 'The assigned executor can perform this task without changing the objective, policy or permissions.',
    'exception_coverage': 'Missing evidence and execution failure have a defined safe review path.',
}
OUTPUT_CHECKS = {
    'task_fidelity': 'The output answers only the assigned task and does not redefine its objective.',
    'grounding': 'Material factual claims cite supplied evidence; gaps and assumptions are explicit; no invented external research or citations.',
    'epistemic_separation': 'Simulated observations are not treated as real-world observations or calibrated success forecasts.',
    'postcondition': 'The stated observable output contract is satisfied.',
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text(value, name, limit=12000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{name} must be nonempty text of at most {limit} characters')
    return value.strip()


def string_list(value, name, maximum=80):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f'{name} must be a bounded list')
    for entry in value:
        text(entry, name)
    return value


def probability(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Probability must be a number')
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Probability must be finite and in [0, 1]')
    return float(value)


def gate(values, threshold):
    threshold = probability(threshold)
    if not values:
        raise ValueError('No validation evidence returned')
    checked = {key: probability(value) for key, value in values.items()}
    return {'passed': all(value >= threshold for value in checked.values()),
            'acceptance_score': min(checked.values()), 'threshold': threshold,
            'dimensions': checked, 'failed_dimensions': [k for k, v in checked.items() if v < threshold],
            'calibration_status': 'unvalidated', 'reliability_probability': None}


def parse_nouls(response, expected):
    answers = response.get('answers')
    if not isinstance(answers, dict) or set(answers) != set(expected):
        raise ValueError('Jev returned missing or unexpected question IDs')
    result = {}
    for key in expected:
        item = answers[key]
        if not isinstance(item, dict) or item.get('type') != 'noul':
            raise ValueError('Jev returned the wrong primitive')
        result[key] = probability(item.get('noul'))
    return result


def validate_question(question):
    if not isinstance(question, dict):
        raise ValueError('Question contract is required')
    text(question.get('instructions'), 'question instructions', 5000)
    kind, criteria = question.get('type'), question.get('criteria')
    if kind == 'choice':
        if not isinstance(criteria, dict) or not 2 <= len(criteria) <= 30 or 'unknown' not in criteria:
            raise ValueError('Choice requires 2-30 options including unknown')
        for key, value in criteria.items():
            text(key, 'choice ID', 60); text(value, 'choice description', 2000)
    elif kind == 'score':
        string_list(criteria, 'score criteria', 10)
        if len(criteria) < 2: raise ValueError('Score needs at least two levels')
    elif kind != 'noul':
        raise ValueError('Unsupported Jev primitive')
    return question


def validate_plan(plan, evidence_ids):
    if not isinstance(plan, dict): raise ValueError('Plan must be an object')
    outcome = plan.get('outcome_contract')
    if not isinstance(outcome, dict): raise ValueError('Outcome Contract is required')
    for field in ('desired_outcome', 'actor_or_owner', 'environment', 'success_observable', 'failure_observable', 'deadline_or_sla'):
        text(outcome.get(field), field)
    for field in ('constraints', 'prohibited_actions', 'required_evidence', 'reversible_actions', 'irreversible_actions', 'human_approval_boundaries'):
        string_list(outcome.get(field), field)
    if outcome['irreversible_actions']:
        raise ValueError('An advisory analysis cannot authorize irreversible actions')
    string_list(plan.get('assumptions'), 'assumptions')
    string_list(plan.get('questions'), 'questions')
    atoms = plan.get('atoms')
    if not isinstance(atoms, list) or not 1 <= len(atoms) <= 12:
        raise ValueError('Plan must contain 1-12 atoms')
    graph = {}
    for atom in atoms:
        if not isinstance(atom, dict): raise ValueError('Atom must be an object')
        identifier = text(atom.get('id'), 'atom ID', 40)
        if not ATOM_ID.fullmatch(identifier) or identifier in graph:
            raise ValueError('Atom IDs must be unique safe identifiers')
        for field in ('objective', 'action', 'object', 'postcondition', 'failure_path'):
            text(atom.get(field), field)
        executor = atom.get('executor')
        if executor not in ('lower_tier', 'frontier', 'jev', 'code', 'human'):
            raise ValueError('Executor is not permitted')
        if atom.get('side_effect') != 'none':
            raise ValueError('This analysis app does not execute business side effects')
        deps = string_list(atom.get('dependencies'), 'dependencies', 12)
        if len(deps) != len(set(deps)): raise ValueError('Duplicate dependency')
        refs = string_list(atom.get('evidence_ids'), 'evidence_ids')
        if not set(refs) <= evidence_ids: raise ValueError('Unknown evidence ID')
        if executor == 'jev': validate_question(atom.get('question_contract'))
        if executor == 'code' and atom.get('operation') != 'evidence_inventory':
            raise ValueError('Only the registered evidence_inventory operation is permitted')
        graph[identifier] = set(deps)
    if any(not deps <= graph.keys() for deps in graph.values()):
        raise ValueError('Unknown dependency')
    try: return list(TopologicalSorter(graph).static_order())
    except CycleError as exc: raise ValueError('DAG contains a cycle') from exc


def validate_repair(old, new, failed_ids):
    if old.get('outcome_contract') != new.get('outcome_contract'):
        raise ValueError('Repair changed the approved outcome or constraints')
    changed = set(failed_ids)
    # Only descendants may be adjusted when a failed dependency changes.
    while True:
        expanded = changed | {a['id'] for a in old['atoms'] if set(a['dependencies']) & changed}
        if expanded == changed: break
        changed = expanded
    new_atoms = {a['id']: a for a in new['atoms']}
    for atom in old['atoms']:
        if atom['id'] not in changed and atom != new_atoms.get(atom['id']):
            raise ValueError('Repair modified an unaffected atom')


def validate_result(value, evidence_ids, source_kinds=None):
    if not isinstance(value, dict): raise ValueError('Analysis output must be an object')
    text(value.get('summary'), 'summary')
    string_list(value.get('assumptions'), 'assumptions')
    string_list(value.get('evidence_gaps'), 'evidence_gaps')
    claims = value.get('claims')
    if not isinstance(claims, list) or len(claims) > 40: raise ValueError('Invalid claims')
    for claim in claims:
        if not isinstance(claim, dict): raise ValueError('Invalid claim')
        text(claim.get('statement'), 'claim')
        if claim.get('kind') not in ('user_supplied', 'simulation_observation', 'inference', 'assumption'):
            raise ValueError('Claim needs an explicit provenance category')
        refs = string_list(claim.get('evidence_ids'), 'claim evidence')
        if not set(refs) <= evidence_ids: raise ValueError('Claim cites nonexistent evidence')
        if claim['kind'] in ('user_supplied', 'simulation_observation'):
            if not refs: raise ValueError('Observed or supplied claims require a source')
            if source_kinds and any(source_kinds.get(ref) != claim['kind'] for ref in refs):
                raise ValueError('A claim cannot change its cited source provenance category')
    return value


def validate_report(value, evidence_ids, source_kinds=None):
    validate_result(value, evidence_ids, source_kinds)
    for field in ('title', 'recommendation'): text(value.get(field), field)
    options = value.get('options')
    if not isinstance(options, list) or not 2 <= len(options) <= 6:
        raise ValueError('Report must compare 2-6 alternatives')
    for option in options:
        if not isinstance(option, dict): raise ValueError('Invalid alternative')
        for field in ('name', 'case_for', 'case_against', 'conditions'):
            text(option.get(field), field)
        if type(option.get('is_status_quo')) is not bool: raise ValueError('Mark status quo explicitly')
    if not any(o['is_status_quo'] for o in options): raise ValueError('Status quo alternative missing')
    swot = value.get('swotmm')
    if not isinstance(swot, dict) or set(swot) != set(SWOTMM): raise ValueError('SWOTMM needs all six sections')
    for name in SWOTMM:
        if not string_list(swot[name], name): raise ValueError('Empty SWOTMM section')
    for name in ('risks', 'next_steps'):
        if not isinstance(value.get(name), list) or not 1 <= len(value[name]) <= 20:
            raise ValueError(f'{name} must contain 1-20 items')
    for risk in value['risks']:
        if not isinstance(risk, dict): raise ValueError('Invalid risk')
        for field in ('risk', 'mitigation'): text(risk.get(field), field)
    for step in value['next_steps']:
        if not isinstance(step, dict): raise ValueError('Invalid next step')
        for field in ('action', 'owner', 'success_check', 'stop_rule'): text(step.get(field), field)
    string_list(value.get('decision_triggers'), 'decision_triggers')
    return value
