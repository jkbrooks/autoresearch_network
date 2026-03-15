# AutoResearch Network

AutoResearch Network is a Bittensor-subnet-style protocol scaffold for decentralized AutoResearch experiments. This repository currently ships the full protocol contract, validation rules, deterministic mock data, a polished no-GPU demo, and minimal neuron scaffolding that can grow into live miner and validator implementations later.

This pass intentionally stops at the protocol foundation. It does not include live chain integration, real miner or validator execution, replay infrastructure, GPU-backed training, or production reward logic.

## What Works Today

- Installable Python package with `autoresearch/` and `neurons/`
- `ExperimentSubmission` synapse contract for validator-to-miner challenge and response exchange
- Centralized protocol constants and hardware tier plausibility ranges
- Deterministic mock submission generation for tests and demos
- Demo CLI via:
  - `python -m autoresearch demo`
  - `python -m autoresearch.protocol demo`
- CI-ready lint, type-check, and test workflow

## Architecture

The current protocol flow is intentionally simple:

1. A validator creates an `ExperimentSubmission` challenge containing the current best `train.py` baseline and best known `val_bpb`.
2. A miner returns a modified `train.py`, its resulting `val_bpb`, self-reported hardware tier, elapsed time, VRAM usage, and a metrics summary log tail.
3. The validator runs protocol validation in a fixed rule order, then previews a demo score using the temporary formula from issue `#7`.

## Repository Layout

```text
autoresearch/
  __main__.py           # package CLI entrypoint
  constants.py          # protocol constants, tiers, plausibility ranges
  protocol.py           # ExperimentSubmission, validation, demo
  mock.py               # deterministic synthetic submissions
  base/                 # thin future-facing neuron scaffolding
  validator/            # reward and forward helpers for the demo surface
neurons/
  miner.py              # importable miner stub
  validator.py          # importable validator stub
tests/
  test_constants.py
  test_protocol.py
.github/workflows/
  ci.yml
```

## Install

Python `>=3.10` is supported. Python 3.11 is the best-tested path for local development.

```bash
uv sync --dev --python 3.11
# `uv sync` installs this project editable inside `.venv`.
uv run pytest

# If you want the plain-pip path from issue #1, verify it explicitly:
python -m pip install -e .
```

## Run The Demo

```bash
python -m autoresearch
python -m autoresearch.protocol
```

The demo is self-contained and does not require a GPU, Bittensor wallet, subnet registration, or network access after dependencies are installed.

## Development Checks

```bash
uv run pytest
uv run ruff check .
uv run mypy autoresearch
```

## Current Public Interfaces

```python
from autoresearch.constants import HardwareTier, TierRange, TIER_PLAUSIBILITY
from autoresearch.protocol import ExperimentSubmission
from autoresearch.mock import MockSubmissionFactory
```

## Reference Repositories

The repositories below are used as design input only and are not vendored here:

- [karpathy/autoresearch](https://github.com/karpathy/autoresearch)
- [mutable-state-inc/autoresearch-at-home](https://github.com/mutable-state-inc/autoresearch-at-home)
- [igbuend/autoresearch-at-home-mlx](https://github.com/igbuend/autoresearch-at-home-mlx)
- [christinetyip/autoresearch-at-home-reports](https://github.com/christinetyip/autoresearch-at-home-reports)
- [ErikDeBruijn/autoresearch-dashboard](https://github.com/ErikDeBruijn/autoresearch-dashboard)
- [ElixirLabsUK/autoresearch-mlx](https://github.com/ElixirLabsUK/autoresearch-mlx)
- [opentensor/bittensor](https://github.com/opentensor/bittensor)
- [opentensor/bittensor-subnet-template](https://github.com/opentensor/bittensor-subnet-template)
- [opentensor/btcli](https://github.com/opentensor/btcli)
- [latent-to/developer-docs](https://github.com/latent-to/developer-docs)
- [karpathy/nanochat](https://github.com/karpathy/nanochat)
- [opentensor/subtensor](https://github.com/opentensor/subtensor)

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for setup, checks, and contribution expectations.
