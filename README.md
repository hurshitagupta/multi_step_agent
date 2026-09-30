# Multi-Step Reasoning

## Overview

This project implements the core behavior of **Multi-Step Reasoning** using a real LLM for execution and mocked model calls for deterministic automated testing.

The implementation covers:

1. Subgoal Decomposition
2. Evidence Tracking
3. Progress Tracking
4. Bounded Backtracking
5. Synthesis

The project also includes validation, step limits, timeouts, retries for transient failures, saved traces, measurements, and safe presentation without exposing hidden chain-of-thought.

---

## Project Structure

```text
multi_step_reasoning/
│
├── subgoal_decomposition.py
├── evidence_tracking.py
├── progress.py
├── bounded_backtracking.py
├── synthesis.py
│
├── tests/
│   ├── test_subgoal_decomposition.py
│   ├── test_evidence_tracking.py
│   ├── test_progress.py
│   ├── test_bounded_backtracking.py
│   └── test_synthesis.py
│
├── outputs/
│   ├── subgoal_decomposition.txt
│   ├── test_subgoal_decomposition.txt
│   ├── evidence_tracking.txt
│   ├── test_evidence_tracking.txt
│   ├── progress.txt
│   ├── test_progress.txt
│   ├── bounded_backtracking.txt
│   ├── test_bounded_backtracking.txt
│   ├── synthesis.txt
│   └── test_synthesis.txt
│
├── .env
├── .gitignore
├── requirements.txt
└── README.md
```

---

# Setup

## 1. Create Virtual Environment

```powershell
python -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\activate
```

---

## 2. Install Dependencies

```powershell
pip install -r requirements.txt
```

---

## 3. Environment Variables

Create a `.env` file:

Credentials are loaded only through environment variables and are not hardcoded in source files.

---

# Task 1 — Subgoal Decomposition

## Objective

Break a larger user request into a small set of clear and manageable subgoals.

The implementation uses a real LLM to generate the subgoals while Python controls validation and limits.

## Run

```powershell
python subgoal_decomposition.py
```

## Run Tests

```powershell
pytest tests/test_subgoal_decomposition.py -v
```
---

# Task 2 — Evidence Tracking

## Objective

Collect and track observable findings that can later support the final response.

Each evidence item contains:

- subgoal
- finding
- source

## Run

```powershell
python evidence_tracking.py
```

## Run Tests

```powershell
pytest tests/test_evidence_tracking.py -v
```
---

# Task 3 — Progress

## Objective

Track the movement of reasoning subgoals through explicit states.

The implementation tracks:

```text
pending
completed
failed
```

Each subgoal is processed individually using the LLM while Python controls the progress loop.

A processed step can be marked completed even when the finding reports that certain information is unavailable. This means the reasoning step was processed successfully, not necessarily that the requested real-world action was completed.

## Run

```powershell
python progress.py
```

## Run Tests

```powershell
pytest tests/test_progress.py -v
```

---

# Task 4 — Bounded Backtracking

## Objective

Allow a failed reasoning step to be revised and attempted again while enforcing a strict backtracking limit.

If a subgoal cannot be completed, the model may suggest a narrower or safer replacement subgoal.

Example flow:

```text
Attempt 1
confirm exact shipping status
→ failed

Backtrack 1
identify available shipping information
→ completed
```

Python controls how many backtracks are allowed.

## Retry vs Backtracking

Retry is used for temporary technical failures such as provider errors.

Backtracking is used when the reasoning step itself cannot be completed and must be revised.

## Run

```powershell
python bounded_backtracking.py
```

## Run Tests

```powershell
pytest tests/test_bounded_backtracking.py -v
```
---

# Task 5 — Synthesis

## Objective

Generate a concise final response using only validated evidence collected during the reasoning process.

The model receives:

- original user request
- validated evidence

It is instructed not to invent missing facts.

Example evidence:

```text
Order 88213 is referenced.
No verified current order status is available.
The customer wants the next step explained.
```

Possible final response:

```text
Order 88213 has been identified, but its current status cannot be verified from the available information. The next step is to retrieve its status from the appropriate order system before confirming the resolution.
```

## Run

```powershell
python synthesis.py
```

## Run Tests

```powershell
pytest tests/test_synthesis.py -v
```

---

# Run All Tests

```powershell
pytest -v
```

---

# Guardrails

The assessment requires guardrails across all tasks.

## Step Limits

Hard limits are used where loops or repeated reasoning can occur.

Examples:

```text
MAX_SUBGOALS
MAX_STEPS
MAX_BACKTRACKS
MAX_EVIDENCE_ITEMS
```

These prevent uncontrolled execution.

## Timeout

All external LLM calls use an HTTP timeout.

```python
timeout=TIMEOUT_SECONDS
```

This prevents a provider request from hanging indefinitely.

## Retry

Retries are only performed for classified transient provider failures such as:

```text
429
500
502
503
504
```

Retries are capped using:

```text
MAX_RETRIES
```

Validation failures are not retried.

## Validation

Inputs and LLM outputs are validated before being accepted.

Examples include:

- empty request rejection
- invalid subgoal rejection
- invalid model status rejection
- missing evidence rejection
- evidence-limit enforcement
- invalid final synthesis rejection

## Secret Hygiene

API credentials are loaded from `.env`.

No API keys are hardcoded in the source code.

The `.env` file should be excluded through `.gitignore`.

---

# Safe Presentation

The implementation does not expose hidden chain-of-thought.

Only reviewable information is stored or displayed, including:

- subgoals
- evidence
- findings
- progress states
- attempt results
- retry counts
- backtrack counts
- limitations
- final answers

This provides traceability without exposing private internal reasoning.

---

# Measurements

The implementation records measurable evidence such as:

- number of subgoals
- number of evidence items
- steps used
- failed/completed steps
- backtracks used
- retry count
- operation latency in milliseconds

These measurements are included in the saved output traces.

---

# Testing Approach

The actual Python files use real LLM calls.

Automated tests mock the model call using `monkeypatch`.

This keeps the tests:

- deterministic
- fast
- repeatable
- independent of API availability
- free from unnecessary API cost

The tests cover both successful execution and failure/rejection paths.