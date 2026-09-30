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

MAX_SUBGOALS = 5
TIMEOUT_SECONDS = 15
MAX_RETRIES = 2

API_KEY = os.getenv("API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME")
BASE_URL = os.getenv("BASE_URL")


class TransientModelError(Exception):
    """Temporary model/provider failure that may be retried."""

@dataclass
class DecompositionResult:
    request: str
    subgoals: list[str]
    status: str
    subgoal_count: int
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


def call_model(request: str) -> list[str]:
    validate_model_config()

    prompt = f"""
Break the following user request into a small set of clear execution subgoals.

Request: {request}

Rules:
- Return between 2 and {MAX_SUBGOALS} subgoals.
- Each subgoal must be short and actionable.
- Do not include hidden reasoning or chain-of-thought.
- Do not explain your reasoning.
- Return JSON only.

Required format:
{{
    "subgoals": [
        "subgoal 1",
        "subgoal 2"
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
            "messages": [
                {"role": "system", "content": ("You are a planning assistant that converts user requests into concise observable subgoals.")},
                {"role": "user", "content": prompt}],"temperature": 0
        },timeout=TIMEOUT_SECONDS)

    if response.status_code in {429, 500, 502, 503, 504}:
        raise TransientModelError(f"Temporary provider failure: HTTP {response.status_code}")

    response.raise_for_status()

    data = response.json()

    content = data["choices"][0]["message"]["content"].strip()

    if content.startswith("```"):
        content = content.replace("```json", "").replace("```", "").strip()

    parsed = json.loads(content)

    subgoals = parsed.get("subgoals")

    if not isinstance(subgoals, list):
        raise ValueError("Model output must contain a subgoals list.")

    return subgoals

def validate_subgoals(subgoals: list[str]) -> None:
    if not subgoals:
        raise ValueError("No subgoals were generated.")

    if len(subgoals) > MAX_SUBGOALS:
        raise ValueError(f"Subgoal limit exceeded. Maximum is {MAX_SUBGOALS}.")

    for subgoal in subgoals:
        if not isinstance(subgoal, str) or not subgoal.strip():
            raise ValueError("Every subgoal must be a non-empty string.")

def decompose_request(request: str) -> DecompositionResult:
    validate_request(request)

    start_time = time.perf_counter()
    retries = 0

    while True:
        try:
            subgoals = call_model(request)
            validate_subgoals(subgoals)
            duration_ms = (time.perf_counter() - start_time) * 1000

            return DecompositionResult(
                request=request,
                subgoals=subgoals,
                status="completed",
                subgoal_count=len(subgoals),
                retries=retries,
                duration_ms=round(duration_ms, 2),
                message="Request successfully decomposed by the model.",
            )

        except TransientModelError as error:
            retries += 1

            if retries > MAX_RETRIES:
                raise RuntimeError(f"Retry limit reached: {error}") from error

            time.sleep(0.5 * retries)


def save_trace(result: DecompositionResult) -> None:
    output_path = OUTPUT_DIR / "subgoal_decomposition.txt"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(asdict(result), file, indent=2)


def main() -> None:
    request = "Resolve order 88213 and tell the customer what happens next."

    result = decompose_request(request)

    save_trace(result)

    print("Status:", result.status)
    print("Request:", result.request)

    print("\nGenerated subgoals:")

    for index, subgoal in enumerate(result.subgoals, start=1):
        print(f"{index}. {subgoal}")

    print("\nSubgoal count:", result.subgoal_count)
    print("Retries:", result.retries)
    print("Duration:", result.duration_ms, "ms")

    print("\nTrace saved to outputs/subgoal_decomposition.txt")


if __name__ == "__main__":
    main()