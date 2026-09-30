import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

TIMEOUT_SECONDS = 15
MAX_RETRIES = 2
MAX_EVIDENCE_ITEMS = 5

API_KEY = os.getenv("API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME")
BASE_URL = os.getenv("BASE_URL")

class TransientModelError(Exception):
    """Temporary provider/model failure that may be retried."""

@dataclass
class EvidenceItem:
    finding: str
    source: str

@dataclass
class SynthesisResult:
    request: str
    answer: str
    status: str
    evidence_count: int
    retries: int
    duration_ms: float
    message: str

def validate_request(request: str) -> None:
    if not isinstance(request, str):
        raise ValueError("Request must be a string.")

    if not request.strip():
        raise ValueError("Request cannot be empty.")

    if len(request) > 300:
        raise ValueError("Request exceeds 300 characters.")


def validate_model_config() -> None:
    if not API_KEY:
        raise ValueError("API_KEY is missing.")

    if not MODEL_NAME:
        raise ValueError("MODEL_NAME is missing.")

    if not BASE_URL:
        raise ValueError("BASE_URL is missing.")


def validate_evidence(evidence: list[EvidenceItem]) -> None:
    if not isinstance(evidence, list):
        raise ValueError("Evidence must be provided as a list.")

    if not evidence:
        raise ValueError("At least one evidence item is required.")

    if len(evidence) > MAX_EVIDENCE_ITEMS:
        raise ValueError(f"Evidence limit exceeded. Maximum is {MAX_EVIDENCE_ITEMS}.")

    for item in evidence:
        if not isinstance(item, EvidenceItem):
            raise ValueError("Every evidence item must be an EvidenceItem.")

        if not item.finding.strip():
            raise ValueError("Evidence finding cannot be empty.")

        if not item.source.strip():
            raise ValueError("Evidence source cannot be empty.")

def call_model(request: str, evidence: list[EvidenceItem]) -> dict:
    validate_model_config()

    evidence_payload = [{"finding": item.finding, "source": item.source} for item in evidence]

    prompt = f""" Create a concise final response for the user.

User request: {request}
Validated evidence: {json.dumps(evidence_payload, indent=2)}

Rules:
- Use only the supplied evidence.
- Do not invent missing facts.
- If important information is unavailable, state that limitation.
- Do not expose hidden chain-of-thought.
- Keep the answer concise and user-facing.
- Return JSON only.

Required format:
{{"answer": "final concise answer"}}
"""

    response = requests.post(
        f"{BASE_URL.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}","Content-Type": "application/json"},
        json={
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content":"You are a synthesis assistant.Produce a final answer using only validated evidence."},
                {"role": "user","content": prompt}],"temperature": 0},timeout=TIMEOUT_SECONDS)

    if response.status_code in {429, 500, 502, 503, 504}:
        raise TransientModelError(f"Temporary provider failure: HTTP {response.status_code}")

    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"].strip()

    if content.startswith("```"):
        content = (content.replace("```json", "").replace("```", "").strip())

    return json.loads(content)

def validate_model_output(result: dict) -> str:
    if not isinstance(result, dict):
        raise ValueError("Model output must be an object.")

    answer = result.get("answer")

    if not isinstance(answer, str):
        raise ValueError("Model output must contain an answer string.")

    if not answer.strip():
        raise ValueError("Synthesized answer cannot be empty.")

    return answer.strip()

def synthesize_answer( request: str, evidence: list[EvidenceItem]) -> SynthesisResult:
    validate_request(request)
    validate_evidence(evidence)

    start_time = time.perf_counter()
    retries = 0

    while True:
        try:
            raw_result = call_model( request=request, evidence=evidence)
            answer = validate_model_output(raw_result)
            duration_ms = (time.perf_counter() - start_time) * 1000

            return SynthesisResult(
                request=request,
                answer=answer,
                status="completed",
                evidence_count=len(evidence),
                retries=retries,
                duration_ms=round(duration_ms, 2),
                message=("Final answer successfully synthesized from validated evidence."))

        except TransientModelError as error:
            retries += 1

            if retries > MAX_RETRIES:
                raise RuntimeError(f"Retry limit reached: {error}") from error

            time.sleep(0.5 * retries)

def save_trace(result: SynthesisResult) -> None:
    output_path = (OUTPUT_DIR / "synthesis.txt")

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump( asdict(result), file,indent=2)

def main() -> None:
    request = "Resolve order 88213 and tell the customer what happens next."

    evidence = [
        EvidenceItem(finding=("The request references order 88213."),source="user request"),
        EvidenceItem(finding=("No verified current order status is available"),source="reasoning step"),
        EvidenceItem(finding=("The customer wants an explanation of the next step."), source="user request")]

    result = synthesize_answer( request=request, evidence=evidence)

    save_trace(result)

    print("Status:", result.status)
    print("Request:", result.request)

    print("\nFinal answer:")
    print(result.answer)

    print("\nEvidence count:", result.evidence_count)
    print("Retries:", result.retries)
    print("Duration:", result.duration_ms, "ms")

if __name__ == "__main__":
    main()