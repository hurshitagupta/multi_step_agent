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
MAX_BACKTRACKS = 2

API_KEY = os.getenv("API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME")
BASE_URL = os.getenv("BASE_URL")

class TransientModelError(Exception):
    """Temporary provider failure that can be retried."""

@dataclass
class AttemptResult:
    attempt: int
    subgoal: str
    status: str
    finding: str

@dataclass
class BacktrackingResult:
    request: str
    original_subgoal: str
    final_subgoal: str
    status: str
    attempts: list[AttemptResult] = field(default_factory=list)
    backtracks_used: int = 0
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

def validate_subgoal(subgoal: str) -> None:
    if not isinstance(subgoal, str):
        raise ValueError("Subgoal must be a string.")

    if not subgoal.strip():
        raise ValueError("Subgoal cannot be empty.")

def validate_model_config() -> None:
    if not API_KEY:
        raise ValueError("API_KEY is missing.")

    if not MODEL_NAME:
        raise ValueError("MODEL_NAME is missing.")

    if not BASE_URL:
        raise ValueError("BASE_URL is missing.")

def call_model(request: str, subgoal: str, attempt: int) -> dict:
    validate_model_config()
    prompt = f"""You are processing one subgoal in a multi-step task.
Overall request: {request}
Current subgoal: {subgoal}
Attempt number: {attempt}
Evaluate whether this subgoal can be completed using only the
information available in the request.
If it cannot be completed, return a concise safer or narrower
replacement subgoal that could be tried next.
Rules:
- status must be either "completed" or "failed"
- finding must be concise and observable
- revised_subgoal is required only when status is "failed"
- do not expose hidden chain-of-thought
- return JSON only

Completed format:
{{
    "status": "completed",
    "finding": "short result"
}}

Failed format:
{{
    "status": "failed",
    "finding": "why the current subgoal cannot be completed",
    "revised_subgoal": "safer or narrower replacement subgoal"
}}
"""

    response = requests.post(
        f"{BASE_URL.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL_NAME, 
              "messages": [{"role": "system", "content": ("You are a bounded backtracking assistant. Evaluate one step at a time and suggest a revised subgoal only when the current one fails.")},
                {"role": "user", "content": prompt}], "temperature": 0}, timeout=TIMEOUT_SECONDS)

    if response.status_code in {429, 500, 502, 503, 504}:
        raise TransientModelError(f"Temporary provider failure: HTTP {response.status_code}")

    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"].strip()

    if content.startswith("```"):
        content = (content.replace("```json", "").replace("```", "").strip())

    return json.loads(content)

def validate_model_result(result: dict) -> dict:
    if not isinstance(result, dict):
        raise ValueError("Model result must be an object.")

    status = result.get("status")
    finding = result.get("finding")

    if status not in {"completed", "failed"}:
        raise ValueError("Status must be either 'completed' or 'failed'.")

    if not isinstance(finding, str) or not finding.strip():
        raise ValueError("Finding must be a non-empty string.")

    if status == "failed":
        revised_subgoal = result.get("revised_subgoal")

        if (not isinstance(revised_subgoal, str) or not revised_subgoal.strip()):
            raise ValueError("Failed result must contain a valid revised_subgoal.")

    return result

def process_with_retry(request: str, subgoal: str, attempt: int) -> tuple[dict, int]:
    retries = 0
    while True:
        try:
            result = call_model(request=request, subgoal=subgoal, attempt=attempt)

            return validate_model_result(result), retries

        except TransientModelError as error:
            retries += 1

            if retries > MAX_RETRIES:
                raise RuntimeError(f"Retry limit reached: {error}") from error
            time.sleep(0.5 * retries)

def bounded_backtrack(request: str, subgoal: str) -> BacktrackingResult:

    validate_request(request)
    validate_subgoal(subgoal)

    start_time = time.perf_counter()

    current_subgoal = subgoal
    attempts = []
    backtracks_used = 0
    total_retries = 0
    attempt_number = 1

    while True:
        result, retries = process_with_retry(request=request, subgoal=current_subgoal, attempt=attempt_number)

        total_retries += retries

        attempts.append(AttemptResult(
                attempt=attempt_number,
                subgoal=current_subgoal,
                status=result["status"],
                finding=result["finding"]))

        if result["status"] == "completed":
            duration_ms = (time.perf_counter() - start_time) * 1000

            return BacktrackingResult(
                request=request,
                original_subgoal=subgoal,
                final_subgoal=current_subgoal,
                status="completed",
                attempts=attempts,
                backtracks_used=backtracks_used,
                retries=total_retries,
                duration_ms=round(duration_ms, 2),
                message="Subgoal completed within backtracking limit.",
            )

        if backtracks_used >= MAX_BACKTRACKS:
            duration_ms = (time.perf_counter() - start_time) * 1000

            return BacktrackingResult(
                request=request,
                original_subgoal=subgoal,
                final_subgoal=current_subgoal,
                status="backtrack_limit_reached",
                attempts=attempts,
                backtracks_used=backtracks_used,
                retries=total_retries,
                duration_ms=round(duration_ms, 2),
                message=("Subgoal could not be completed within the allowed backtracking limit."))

        current_subgoal = result["revised_subgoal"]
        backtracks_used += 1
        attempt_number += 1

def save_trace(result: BacktrackingResult) -> None:
    output_path = OUTPUT_DIR / "bounded_backtracking.txt"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(asdict(result), file, indent=2)

def main() -> None:
    request = ("Resolve order 88213 and tell the customer what happens next.")

    subgoal = "confirm the exact current shipping status"

    result = bounded_backtrack(request=request, subgoal=subgoal)

    save_trace(result)

    print("Overall status:", result.status)
    print("Original subgoal:", result.original_subgoal)
    print("Final subgoal:", result.final_subgoal)

    print("\nAttempts:")

    for attempt in result.attempts:
        print(
            f"Attempt {attempt.attempt}: "
            f"{attempt.subgoal} -> "
            f"{attempt.status} -> "
            f"{attempt.finding}"
        )

    print("\nBacktracks used:", result.backtracks_used)
    print("Retries:", result.retries)
    print("Duration:", result.duration_ms, "ms")

    print("\nTrace saved to outputs/bounded_backtracking.txt")


if __name__ == "__main__":
    main()