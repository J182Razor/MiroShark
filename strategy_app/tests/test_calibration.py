import importlib.util
import pytest


def test_metrics_do_not_turn_small_perfect_sample_into_reliability_claim():
    assert importlib.util.find_spec('strategy_app.calibration'), 'Evaluation utility must exist'
    from strategy_app.calibration import evaluate
    result=evaluate([{'score':.99,'label':True} for _ in range(10)],.95)
    assert result['accepted_case_precision']==1
    assert result['precision_lower_95']<.95
    assert result['reliability_claim']=='none'


def test_brier_and_empty_acceptance_are_explicit():
    assert importlib.util.find_spec('strategy_app.calibration'), 'Evaluation utility must exist'
    from strategy_app.calibration import evaluate
    result=evaluate([{'score':.9,'label':True},{'score':.1,'label':False}],.95)
    assert result['brier']==pytest.approx(.01)
    assert result['accepted_case_precision'] is None
    assert result['coverage']==0
