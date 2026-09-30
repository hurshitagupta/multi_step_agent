import json
import os
import time
from dataclasses import dataclass, asdict, field
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
    """Temporary model/provider failure that can be retried."""

@dataclass
class EvidenceItem:
    subgoal: str
    finding: str
    source: str

@dataclass
class EvidenceResult:
    request: str
    evidence: list[EvidenceItem] = field(default_factory=list)
    status: str = "pending"
    evidence_count: int = 0
    retries: int = 0
    duration_ms: float = 0.0
    message: str = ""


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


def call_model(request: str) -> list[dict]:
    validate_model_config()

    prompt = f"""
Analyze the following user request and return concise observable evidence
that can support a final answer.

Request: {request}

Rules:
- Return between 1 and {MAX_EVIDENCE_ITEMS} evidence items.
- Each item must contain:
  - subgoal
  - finding
  - source
- The source should explain where the finding came from, such as:
  "user request", "provided context", or "model analysis".
- Do not expose hidden chain-of-thought.
- Do not explain internal reasoning.
- Return JSON only.

Required format:
{{
    "evidence": [
        {{
            "subgoal": "short subgoal",
            "finding": "observable finding",
            "source": "source of finding"
        }}
    ]
}}
"""

    response = requests.post(
        f"{BASE_URL.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL_NAME,
            "messages": [{"role": "system", "content": ("You are an evidence-tracking assistant. Return only concise findings that can be verified or safely presented to the user.")},
                {"role": "user", "content": prompt}],"temperature": 0,
        },timeout=TIMEOUT_SECONDS)

    if response.status_code in {429, 500, 502, 503, 504}:
        raise TransientModelError(f"Temporary provider failure: HTTP {response.status_code}")

    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"].strip()

    if content.startswith("```"):
        content = (content.replace("```json", "").replace("```", "").strip())

    parsed = json.loads(content)

    evidence = parsed.get("evidence")

    if not isinstance(evidence, list):
        raise ValueError("Model output must contain an evidence list.")

    return evidence

def validate_evidence(evidence: list[dict]) -> list[EvidenceItem]:
    if not evidence:
        raise ValueError("No evidence was returned.")

    if len(evidence) > MAX_EVIDENCE_ITEMS:
        raise ValueError(f"Evidence limit exceeded. Maximum is {MAX_EVIDENCE_ITEMS}.")

    validated_items = []

    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("Each evidence item must be an object.")

        subgoal = item.get("subgoal")
        finding = item.get("finding")
        source = item.get("source")

        if not isinstance(subgoal, str) or not subgoal.strip():
            raise ValueError("Each evidence item must contain a valid subgoal.")

        if not isinstance(finding, str) or not finding.strip():
            raise ValueError("Each evidence item must contain a valid finding.")

        if not isinstance(source, str) or not source.strip():
            raise ValueError("Each evidence item must contain a valid source.")

        validated_items.append(EvidenceItem(subgoal=subgoal.strip(), finding=finding.strip(), source=source.strip()))

    return validated_items

def track_evidence(request: str) -> EvidenceResult:
    validate_request(request)

    start_time = time.perf_counter()
    retries = 0

    while True:
        try:
            raw_evidence = call_model(request)
            evidence = validate_evidence(raw_evidence)
            duration_ms = (time.perf_counter() - start_time) * 1000

            return EvidenceResult(
                request=request,
                evidence=evidence,
                status="completed",
                evidence_count=len(evidence),
                retries=retries,
                duration_ms=round(duration_ms, 2),
                message="Evidence successfully collected and validated.",
            )

        except TransientModelError as error:
            retries += 1

            if retries > MAX_RETRIES:
                raise RuntimeError(f"Retry limit reached: {error}") from error

            time.sleep(0.5 * retries)

def save_trace(result: EvidenceResult) -> None:
    output_path = OUTPUT_DIR / "evidence_tracking.txt"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(asdict(result), file, indent=2)

def main() -> None:
    request = "Resolve order 88213 and tell the customer what happens next."

    result = track_evidence(request)

    save_trace(result)

    print("Status:", result.status)
    print("Request:", result.request)

    print("\nEvidence:")

    for index, item in enumerate(result.evidence, start=1):
        print(f"\nEvidence {index}")
        print("Subgoal:", item.subgoal)
        print("Finding:", item.finding)
        print("Source:", item.source)

    print("\nEvidence count:", result.evidence_count)
    print("Retries:", result.retries)
    print("Duration:", result.duration_ms, "ms")

    print("\nTrace saved to outputs/evidence_tracking.txt")

if __name__ == "__main__":
    main()