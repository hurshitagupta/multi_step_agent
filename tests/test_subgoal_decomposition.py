import pytest

import subgoal_decomposition
from subgoal_decomposition import TransientModelError, decompose_request

def test_successful_subgoal_decomposition(monkeypatch):
    def fake_model_call(request):
        return [
            "identify order",
            "check order status",
            "check constraints",
            "prepare customer response",
        ]

    monkeypatch.setattr(subgoal_decomposition, "call_model", fake_model_call)
    result = decompose_request("Resolve order 88213")

    assert result.status == "completed"
    assert result.subgoal_count == 4
    assert result.subgoals == [
        "identify order",
        "check order status",
        "check constraints",
        "prepare customer response",
    ]

def test_empty_request_is_rejected():
    with pytest.raises(ValueError,match="Request cannot be empty"):
        decompose_request("")

def test_too_many_subgoals_are_rejected(monkeypatch):
    def fake_model_call(request):
        return ["step 1", "step 2", "step 3", "step 4", "step 5", "step 6"]

    monkeypatch.setattr(subgoal_decomposition, "call_model", fake_model_call)

    with pytest.raises(ValueError, match="Subgoal limit exceeded"):
        decompose_request("Resolve order 88213")


def test_transient_failure_is_retried(monkeypatch):
    attempts = {"count": 0}

    def fake_model_call(request):
        attempts["count"] += 1

        if attempts["count"] == 1:
            raise TransientModelError("Temporary provider failure")

        return ["identify order", "check order status", "prepare response"]

    monkeypatch.setattr(subgoal_decomposition, "call_model", fake_model_call)
    result = decompose_request("Resolve order 88213")

    assert result.status == "completed"
    assert result.retries == 1
    assert attempts["count"] == 2