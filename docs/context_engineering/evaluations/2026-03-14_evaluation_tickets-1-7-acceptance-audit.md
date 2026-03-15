# Acceptance Audit: Issues 1 through 7

Date: 2026-03-14 18:29:14 PDT
Repository: autoresearch_network
Scope: Acceptance criteria only for issues `#1` through `#7`

## Summary

- Overall result: not every acceptance criterion is met.
- Local code and test criteria are met across issues `#3` through `#7`, and most of issue `#1`.
- The remaining unmet criteria are external to the local implementation:
  - issue `#1`: hosted CI does not pass on push to `main`

## Issue 1

- `pip install -e .` succeeds in the codespace: **Met**
  - Verified locally with `pip install -e .`, which completed successfully against the current repo state.
- `pytest` runs (even if no tests yet) without import errors: **Met**
  - Verified locally with `uv run pytest`, which passed and imported the package cleanly.
- CI passes on push to `main`: **Not met**
  - The latest hosted push run on `main` is [23100564941](https://github.com/jkbrooks/autoresearch_network/actions/runs/23100564941), and it failed before job execution because the account is locked for billing.
- README explains what the project is, how to install, and links to all reference repos: **Met**
  - The current README covers project purpose, install flow, demo usage, and the full reference-repo list in [README.md](/Users/m/Desktop/autoresearchnetwork/README.md:1).

## Issue 2

- All tickets above are merged to `main`: **Met**
  - PR [#28](https://github.com/jkbrooks/autoresearch_network/pull/28) is merged into `main`.
- `python -m autoresearch.protocol demo` produces clean, readable output in <5 seconds: **Met**
  - Verified locally; the command exited `0` in `0.946s` and printed the required sections from [protocol.py](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:152).
- `pytest tests/test_protocol.py` passes with 100% coverage of validation logic: **Met**
  - Verified locally with `uv run pytest tests/test_protocol.py`, which passed with 100% coverage on the gated protocol modules.
- No GPU, chain connection, or wallet required for any code in this epic: **Met**
  - The demo and test suite run locally without GPU, wallet, or chain access, and neuron code remains stubbed in [neurons/miner.py](/Users/m/Desktop/autoresearchnetwork/neurons/miner.py:1) and [neurons/validator.py](/Users/m/Desktop/autoresearchnetwork/neurons/validator.py:1).

## Issue 3

- `ExperimentSubmission` class exists in `autoresearch/protocol.py`: **Met**
  - Present in [protocol.py](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:40).
- Can be instantiated with validator fields only: **Met**
  - Covered in [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:65).
- Miner fields default to `None`: **Met**
  - Covered in [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:72).
- `deserialize()` returns a dict with all miner fields: **Met**
  - Implemented in [protocol.py](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:54) and asserted in [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:80).
- Importable from any module: `from autoresearch.protocol import ExperimentSubmission`: **Met**
  - Supported by the package layout and exercised by the test suite.

## Issue 4

- `HardwareTier` enum exists and is importable: **Met**
  - Implemented in [constants.py](/Users/m/Desktop/autoresearchnetwork/autoresearch/constants.py:9).
- `TIER_PLAUSIBILITY` dict maps every tier to a `TierRange`: **Met**
  - Implemented in [constants.py](/Users/m/Desktop/autoresearchnetwork/autoresearch/constants.py:30) and checked in [test_constants.py](/Users/m/Desktop/autoresearchnetwork/tests/test_constants.py:30).
- All scoring constants are defined with comments: **Met**
  - Present in [constants.py](/Users/m/Desktop/autoresearchnetwork/autoresearch/constants.py:37).
- `HardwareTier("small")` returns `HardwareTier.SMALL`: **Met**
  - Covered in [test_constants.py](/Users/m/Desktop/autoresearchnetwork/tests/test_constants.py:18).
- `HardwareTier("invalid")` raises `ValueError`: **Met**
  - Covered in [test_constants.py](/Users/m/Desktop/autoresearchnetwork/tests/test_constants.py:25).

## Issue 5

- `validate()` method exists on `ExperimentSubmission`: **Met**
  - Implemented in [protocol.py](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:66).
- A well-formed submission passes without raising: **Met**
  - Covered in [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:246).
- Each of the 10 rules triggers the correct `ValueError` with the documented message pattern: **Met**
  - Covered across [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:111) through [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:243).
- Rules are checked in the documented order (first failure wins): **Met**
  - The implementation follows the required order in [protocol.py](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:69), and the invalid-variant tests assert the expected first-hit failures.

## Issue 6

- `MockSubmissionFactory` exists in `autoresearch/mock.py`: **Met**
  - Implemented in [mock.py](/Users/m/Desktop/autoresearchnetwork/autoresearch/mock.py:55).
- `make_submission()` returns an `ExperimentSubmission` that passes `validate()` by default: **Met**
  - Covered in [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:252).
- `make_submission(improvement=)` produces `val_bpb < baseline_val_bpb`: **Met**
  - Covered in [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:263).
- `make_submission(improvement=)` produces `val_bpb > baseline_val_bpb`: **Met**
  - Covered in [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:271).
- Each `make_invalid_submission(reason=...)` variant fails `validate()` with the expected `ValueError`: **Met**
  - Covered by the parametrized invalid-variant test in [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:298) plus the dedicated rule-8 isolation test in [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:316).
- Deterministic: same seed produces identical output: **Met**
  - Covered in [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:283).
- No GPU, chain, or network access required: **Met**
  - The factory is pure local data generation and the tests run without external dependencies.

## Issue 7

- `python -m autoresearch demo` works from the codespace: **Met**
  - Verified locally; subprocess test covers this in [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:365).
- Output matches the format above (sections 1–5, with ✓/✗ markers, timing): **Met**
  - The output structure is produced in [protocol.py](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:175), and tests assert the required section markers in [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:381).
- Runs in <5 seconds: **Met**
  - Verified locally; subprocess timing test covers this in [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:365).
- No GPU, chain, wallet, or network access required: **Met**
  - The demo path is built entirely from the local mock factory in [protocol.py](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:155).
- Exit code 0 on success: **Met**
  - Covered in [test_protocol.py](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:397).
- Can be screen-recorded as a hackathon demo without editing: **Met**
  - The current output is clean, sectioned, and colorized from [protocol.py](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:175), with direct local verification via `python -m autoresearch.protocol demo`.
