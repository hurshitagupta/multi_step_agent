import pytest

import progress
from progress import TransientModelError, track_progress

def test_all_subgoals_complete(monkeypatch):
    def fake_model_call(request, subgoal):
        return {"status": "completed", "finding": f"{subgoal} completed successfully."}

    monkeypatch.setattr(progress, "call_model", fake_model_call)

    subgoals = ["identify order", "check order status", "prepare response",]

    result = track_progress("Resolve order 88213", subgoals)

    assert result.status == "completed"
    assert len(result.completed) == 3
    assert result.failed == []
    assert result.pending == []
    assert result.steps_used == 3

def test_failed_subgoal_is_tracked(monkeypatch):
    def fake_model_call(request, subgoal):
        if subgoal == "check order status":
            return {"status": "failed", "finding": "Order status could not be determined."}

        return {"status": "completed", "finding": f"{subgoal} completed."}

    monkeypatch.setattr(progress, "call_model", fake_model_call)

    subgoals = ["identify order", "check order status", "prepare response"]

    result = track_progress("Resolve order 88213", subgoals)

    assert result.status == "completed_with_failures"
    assert "check order status" in result.failed
    assert len(result.completed) == 2

def test_empty_subgoals_are_rejected():
    with pytest.raises(ValueError, match="At least one subgoal is required"):
        track_progress("Resolve order 88213", [])

def test_step_limit_is_enforced():
    subgoals = ["step 1", "step 2", "step 3", "step 4", "step 5", "step 6"]

    with pytest.raises(ValueError, match="Step limit exceeded"):
        track_progress("Resolve order 88213", subgoals)

def test_transient_failure_is_retried(monkeypatch):
    attempts = {"count": 0}

    def fake_model_call(request, subgoal):
        attempts["count"] += 1

        if attempts["count"] == 1:
            raise TransientModelError("Temporary provider failure")

        return {"status": "completed", "finding": "Subgoal completed."}

    monkeypatch.setattr(progress, "call_model", fake_model_call)

    result = track_progress("Resolve order 88213", ["identify order"])

    assert result.status == "completed"
    assert result.retries == 1
    assert attempts["count"] == 2