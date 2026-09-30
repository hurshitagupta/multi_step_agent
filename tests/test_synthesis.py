import pytest

import synthesis
from synthesis import EvidenceItem, TransientModelError, synthesize_answer

def test_successful_synthesis(monkeypatch):
    def fake_model_call(request, evidence):
        return {"answer": "Order 88213 is identified, but its current status is unavailable."}

    monkeypatch.setattr(synthesis, "call_model", fake_model_call)

    evidence = [
        EvidenceItem(finding="Order 88213 is referenced.", source="user request"),
        EvidenceItem(finding=("No verified current order status is available."),source="reasoning step")
        ]

    result = synthesize_answer("Resolve order 88213", evidence)

    assert result.status == "completed"
    assert result.evidence_count == 2
    assert "Order 88213" in result.answer

def test_empty_evidence_is_rejected():
    with pytest.raises(ValueError,match=("At least one evidence item is required")):
        synthesize_answer("Resolve order 88213",[])

def test_invalid_evidence_is_rejected():
    evidence = [EvidenceItem(finding="", source="user request")]

    with pytest.raises(ValueError, match="Evidence finding cannot be empty"):
        synthesize_answer("Resolve order 88213", evidence)

def test_evidence_limit_is_enforced():
    evidence = [EvidenceItem(finding=f"Finding {i}", source="test source")
        for i in range(6)]

    with pytest.raises(ValueError, match="Evidence limit exceeded"):
        synthesize_answer("Resolve order 88213", evidence)

def test_empty_model_answer_is_rejected(monkeypatch):
    def fake_model_call(request, evidence):
        return {"answer": ""}

    monkeypatch.setattr(synthesis, "call_model", fake_model_call)

    evidence = [EvidenceItem(finding="Order 88213 is referenced.", source="user request")]

    with pytest.raises( ValueError, match=("Synthesized answer cannot be empty")):
        synthesize_answer("Resolve order 88213", evidence)

def test_transient_failure_is_retried(monkeypatch):
    attempts = {"count": 0}

    def fake_model_call(request, evidence):
        attempts["count"] += 1

        if attempts["count"] == 1:
            raise TransientModelError("Temporary provider failure")

        return {"answer": "Order 88213 is identified."}

    monkeypatch.setattr(synthesis, "call_model", fake_model_call)

    evidence = [EvidenceItem(finding="Order 88213 is referenced.", source="user request")]

    result = synthesize_answer("Resolve order 88213", evidence)

    assert result.status == "completed"
    assert result.retries == 1
    assert attempts["count"] == 2