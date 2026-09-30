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
MAX_STEPS = 5

API_KEY = os.getenv("API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME")
BASE_URL = os.getenv("BASE_URL")

class TransientModelError(Exception):
    """Temporary provider/model failure that can be retried."""

@dataclass
class StepResult:
    subgoal: str
    status: str
    finding: str

@dataclass
class ProgressState:
    request: str
    pending: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    findings: list[StepResult] = field(default_factory=list)
    steps_used: int = 0
    retries: int = 0
    status: str = "pending"
    duration_ms: float = 0.0
    message: str = ""

def validate_request(request: str) -> None:
    if not isinstance(request, str):
        raise ValueError("Request must be a string.")

    if not request.strip():
        raise ValueError("Request cannot be empty.")

    if len(request) > 300:
        raise ValueError("Request exceeds 300 characters.")

def validate_subgoals(subgoals: list[str]) -> None:
    if not isinstance(subgoals, list):
        raise ValueError("Subgoals must be provided as a list.")

    if not subgoals:
        raise ValueError("At least one subgoal is required.")

    if len(subgoals) > MAX_STEPS:
        raise ValueError(f"Step limit exceeded. Maximum is {MAX_STEPS}.")

    for subgoal in subgoals:
        if not isinstance(subgoal, str) or not subgoal.strip():
            raise ValueError("Every subgoal must be a non-empty string.")
        
def validate_model_config() -> None:
    if not API_KEY:
        raise ValueError("API_KEY is missing.")

    if not MODEL_NAME:
        raise ValueError("MODEL_NAME is missing.")

    if not BASE_URL:
        raise ValueError("BASE_URL is missing.")

def call_model(request: str, subgoal: str) -> dict:
    validate_model_config()

    prompt = f""" You are processing one subgoal from a multi-step task.

Overall request: {request}
Current subgoal: {subgoal}

Evaluate only this subgoal.
Rules:
- Return either "completed" or "failed".
- Give one short observable finding.
- Do not expose chain-of-thought or hidden reasoning.
- Do not explain internal reasoning.
- Return JSON only.

Required format:
{{
    "status": "completed",
    "finding": "short observable result"
}}
"""
    response = requests.post(
        f"{BASE_URL.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL_NAME,
            "messages": [{"role": "system", "content": ("You are a step-processing assistant. Evaluate one explicit subgoal at a time and return only a concise result.")},
                {"role": "user", "content": prompt}],"temperature": 0,
        },timeout=TIMEOUT_SECONDS)

    if response.status_code in {429, 500, 502, 503, 504}:
        raise TransientModelError(f"Temporary provider failure: HTTP {response.status_code}")

    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"].strip()

    if content.startswith("```"):
        content = (content.replace("```json", "").replace("```", "").strip())

    return json.loads(content)

def validate_step_result(result: dict) -> StepResult:
    if not isinstance(result, dict):
        raise ValueError("Model result must be an object.")

    status = result.get("status")
    finding = result.get("finding")

    if status not in {"completed", "failed"}:
        raise ValueError("Step status must be either 'completed' or 'failed'.")

    if not isinstance(finding, str) or not finding.strip():
        raise ValueError("Step finding must be a non-empty string.")

    return StepResult(subgoal="", status=status, finding=finding.strip())

def process_subgoal(request: str, subgoal: str) -> tuple[StepResult, int]:

    retries = 0

    while True:
        try:
            raw_result = call_model(request, subgoal)
            result = validate_step_result(raw_result)
            result.subgoal = subgoal

            return result, retries

        except TransientModelError as error:
            retries += 1

            if retries > MAX_RETRIES:
                raise RuntimeError(f"Retry limit reached: {error}") from error
            time.sleep(0.5 * retries)

def track_progress(request: str, subgoals: list[str]) -> ProgressState:

    validate_request(request)
    validate_subgoals(subgoals)

    start_time = time.perf_counter()

    state = ProgressState(request=request, pending=subgoals.copy())

    while state.pending and state.steps_used < MAX_STEPS:
        current_subgoal = state.pending.pop(0)
        result, retries = process_subgoal(request, current_subgoal)

        state.retries += retries
        state.steps_used += 1
        state.findings.append(result)

        if result.status == "completed":
            state.completed.append(current_subgoal)

        else:
            state.failed.append(current_subgoal)

    state.duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    if state.pending:
        state.status = "step_limit_reached"
        state.message = "Progress stopped because the step limit was reached."

    elif state.failed:
        state.status = "completed_with_failures"
        state.message = "All allowed subgoals were processed,but at least one failed."

    else:
        state.status = "completed"
        state.message = "All subgoals were successfully processed."

    return state

def save_trace(state: ProgressState) -> None:
    output_path = OUTPUT_DIR / "progress.txt"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(asdict(state), file, indent=2)

def main() -> None:
    request = "Resolve order 88213 and tell the customer what happens next."

    subgoals = [
        "identify order",
        "check order status",
        "check applicable constraints",
        "prepare customer response",
    ]

    state = track_progress(request=request, subgoals=subgoals,)

    save_trace(state)

    print("Overall status:", state.status)
    print("Request:", state.request)

    print("\nCompleted:")
    for item in state.completed:
        print("-", item)

    print("\nFailed:")
    for item in state.failed:
        print("-", item)

    print("\nPending:")
    for item in state.pending:
        print("-", item)

    print("\nFindings:")
    for result in state.findings:
        print(f"- {result.subgoal}: {result.status} -> {result.finding}")

    print("\nSteps used:", state.steps_used)
    print("Retries:", state.retries)
    print("Duration:", state.duration_ms, "ms")
    print("\nTrace saved to outputs/progress.txt")

if __name__ == "__main__":
    main()