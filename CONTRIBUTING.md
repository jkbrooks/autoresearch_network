# Contributing

## Scope

This repository currently focuses on the AutoResearch Network protocol layer. Changes in this stage should keep the package self-contained and runnable without GPU, wallet, or chain access.

## Local Setup

```bash
uv sync --dev --python 3.11
# `uv sync` installs the repo editable inside `.venv`.
uv run pytest

# If you want to exercise the plain-pip acceptance path directly:
python -m pip install -e .
```

## Before You Open A PR

Run the full local checks:

```bash
uv run pytest
uv run ruff check .
uv run mypy autoresearch
python -m autoresearch demo
```

## Coding Expectations

- Keep public interfaces typed and stable.
- Put shared thresholds and plausibility ranges in `autoresearch/constants.py`.
- Preserve the documented validation order in `ExperimentSubmission.validate()`.
- Keep demo behavior deterministic and self-contained.
- Treat neuron code under `neurons/` and `autoresearch/base/` as scaffolding unless the issue explicitly expands subnet behavior.

## Pull Request Guidance

- Link the issue numbers you are implementing or fixing.
- Summarize protocol changes, validation changes, and any public interface changes.
- Call out whether the demo output or README changed.
- Do not vendor reference repositories into this repo.

## Testing Guidance

- Add protocol behavior tests in `tests/test_protocol.py`.
- Add constants-focused assertions in `tests/test_constants.py` when new thresholds or tiers are introduced.
- Prefer deterministic test data and seeded factories over hand-built random payloads.
