"""Tests for safe condition evaluation in task integration pipeline adapter."""

import pytest

from modules.tasks.task_integration import _safe_eval_condition


def test_safe_eval_condition_allows_outputs_get_and_compare():
    outputs = {"status": "ready", "count": 3}
    assert _safe_eval_condition("outputs.get('status') == 'ready' and outputs['count'] >= 3", outputs)


def test_safe_eval_condition_allows_len():
    outputs = {"items": [1, 2, 3]}
    assert _safe_eval_condition("len(outputs.get('items', [])) == 3", outputs)


def test_safe_eval_condition_rejects_unsafe_calls():
    outputs = {"x": 1}
    with pytest.raises(ValueError):
        _safe_eval_condition("__import__('os').system('echo hacked')", outputs)
