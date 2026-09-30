import pytest

import evidence_tracking
from evidence_tracking import TransientModelError, track_evidence

def test_successful_evidence_tracking(monkeypatch):
    def fake_model_call(request):
        return [{"subgoal": "identify order",
                "finding": "The request references order 88213.",
                "source": "user request"},
                {"subgoal": "identify requested action",
                "finding": "The customer wants the order resolved and next steps explained.",
                "source": "user request"}]

    monkeypatch.setattr(evidence_tracking, "call_model", fake_model_call)

    result = track_evidence("Resolve order 88213 and explain what happens next.")

    assert result.status == "completed"
    assert result.evidence_count == 2
    assert result.evidence[0].subgoal == "identify order"
    assert result.evidence[0].source == "user request"

def test_empty_request_is_rejected():
    with pytest.raises(ValueError, match="Request cannot be empty"):
        track_evidence("")

def test_invalid_evidence_is_rejected(monkeypatch):
    def fake_model_call(request):
        return [{
                "subgoal": "identify order",
                "finding": "",
                "source": "user request",
            }]

    monkeypatch.setattr(evidence_tracking, "call_model", fake_model_call)

    with pytest.raises(ValueError, match="valid finding"):
        track_evidence("Resolve order 88213")

def test_evidence_limit_is_enforced(monkeypatch):
    def fake_model_call(request):
        return [{
                "subgoal": f"subgoal {i}",
                "finding": f"finding {i}",
                "source": "test source"
            }for i in range(6)]

    monkeypatch.setattr(evidence_tracking, "call_model",fake_model_call)

    with pytest.raises(ValueError, match="Evidence limit exceeded"):
        track_evidence("Resolve order 88213")

def test_transient_failure_is_retried(monkeypatch):
    attempts = {"count": 0}

    def fake_model_call(request):
        attempts["count"] += 1

        if attempts["count"] == 1:
            raise TransientModelError("Temporary provider failure")

        return [{
                "subgoal": "identify order",
                "finding": "Order 88213 is referenced.",
                "source": "user request",
            }]

    monkeypatch.setattr(evidence_tracking, "call_model", fake_model_call)

    result = track_evidence("Resolve order 88213")

    assert result.status == "completed"
    assert result.retries == 1
    assert attempts["count"] == 2