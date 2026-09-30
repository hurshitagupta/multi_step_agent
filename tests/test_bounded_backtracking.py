import pytest

import bounded_backtracking
from bounded_backtracking import TransientModelError, bounded_backtrack


def test_subgoal_completes_without_backtracking(monkeypatch):
    def fake_model_call(request, subgoal, attempt):
        return {"status": "completed", "finding": "Order 88213 is present in the request."}

    monkeypatch.setattr(bounded_backtracking, "call_model", fake_model_call)

    result = bounded_backtrack("Resolve order 88213", "identify order")

    assert result.status == "completed"
    assert result.backtracks_used == 0
    assert len(result.attempts) == 1


def test_failed_subgoal_backtracks_and_completes(monkeypatch):
    responses = [{
            "status": "failed",
            "finding": "Exact shipping status is unavailable.",
            "revised_subgoal": "identify available shipping information",
        },
        {
            "status": "completed",
            "finding": "No verified shipping status is present in the request."}]

    def fake_model_call(request, subgoal, attempt):
        return responses[attempt - 1]

    monkeypatch.setattr(bounded_backtracking, "call_model", fake_model_call)

    result = bounded_backtrack("Resolve order 88213", "confirm exact shipping status")

    assert result.status == "completed"
    assert result.backtracks_used == 1
    assert len(result.attempts) == 2
    assert (result.final_subgoal == "identify available shipping information")

def test_backtracking_limit_is_enforced(monkeypatch):
    def fake_model_call(request, subgoal, attempt):
        return {
            "status": "failed",
            "finding": "Required information is unavailable.",
            "revised_subgoal": f"revised subgoal {attempt}",
        }

    monkeypatch.setattr(bounded_backtracking, "call_model", fake_model_call)

    result = bounded_backtrack("Resolve order 88213", "confirm shipping status")

    assert result.status == "backtrack_limit_reached"
    assert result.backtracks_used == 2
    assert len(result.attempts) == 3

def test_empty_subgoal_is_rejected():
    with pytest.raises( ValueError, match="Subgoal cannot be empty"):
        bounded_backtrack("Resolve order 88213","")

def test_transient_failure_is_retried(monkeypatch):
    attempts = {"count": 0}

    def fake_model_call(request, subgoal, attempt):
        attempts["count"] += 1

        if attempts["count"] == 1:
            raise TransientModelError("Temporary provider failure")

        return {
            "status": "completed",
            "finding": "Subgoal completed after retry.",
        }

    monkeypatch.setattr(bounded_backtracking, "call_model", fake_model_call)

    result = bounded_backtrack( "Resolve order 88213", "identify order")

    assert result.status == "completed"
    assert result.retries == 1
    assert attempts["count"] == 2