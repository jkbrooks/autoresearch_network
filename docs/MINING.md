# MINING.md

This guide takes a new miner from zero to a running AutoResearch miner on testnet.

## Requirements

- Ubuntu 22.04+ recommended
- NVIDIA GPU with at least 8GB VRAM
- Python 3.10+
- `uv`
- roughly 10GB free disk
- stable internet connection

## Install

```bash
git clone https://github.com/jkbrooks/autoresearch_network.git
cd autoresearch_network
python -m pip install -e .
uv sync --python 3.11
```

- `git clone` downloads the repository.
- `python -m pip install -e .` installs the package in editable mode.
- `uv sync` installs the locked Python dependencies.

## One-Time Data Setup

```bash
uv run prepare.py
```

This downloads the training data, trains the tokenizer, and caches assets in `~/.cache/autoresearch/`. It is only needed once per machine.

## Create Wallet

```bash
btcli wallet new_coldkey --wallet.name my-miner
btcli wallet new_hotkey --wallet.name my-miner --wallet.hotkey default
```

- The coldkey is your long-lived identity and should be backed up immediately.
- The hotkey is the operational key the miner process uses.
- Wallet files are stored under `~/.bittensor/wallets/`.

## Get Test TAO

- Join the Bittensor Discord: https://discord.gg/bittensor
- Ask in the faucet channel for test TAO
- Budget about 100 test TAO for registration and experimentation

## Register on Testnet

```bash
btcli subnet register --netuid <NETUID> --network test \
  --wallet.name my-miner --wallet.hotkey default
```

Replace `<NETUID>` with the deployed testnet subnet ID.

## Configure LLM Mutations (Optional)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

or

```bash
export OPENAI_API_KEY="sk-..."
```

Without an API key the miner uses the built-in structured mutation strategy.

### API cost budgeting

| Provider | Cost per experiment | Cost per hour | Cost per day |
| --- | --- | --- | --- |
| Anthropic Claude Opus | ~$0.06 | ~$0.72 | ~$17 |
| OpenAI GPT-4o | ~$0.02 | ~$0.24 | ~$6 |
| Local / compatible endpoint | $0 | $0 | $0 |

You can use a compatible local endpoint with:

```bash
python neurons/miner.py \
  --mutation-provider openai-compatible \
  --mutation-base-url http://localhost:8000
```

## Run the Miner

With structured mutations:

```bash
python neurons/miner.py \
  --netuid <NETUID> \
  --network test \
  --wallet.name my-miner \
  --wallet.hotkey default \
  --logging.debug
```

With an LLM provider:

```bash
python neurons/miner.py \
  --netuid <NETUID> \
  --network test \
  --wallet.name my-miner \
  --wallet.hotkey default \
  --mutation-provider anthropic \
  --logging.debug
```

Run under `tmux` or `screen` for persistence.

## Verify You Are Earning

```bash
btcli wallet overview --wallet.name my-miner --network test
```

Look for:
- a non-zero `EMISSION`
- non-zero `INCENTIVE`
- a populated `RANK`

## Troubleshooting

| Problem | Solution |
| --- | --- |
| No CUDA GPU detected | Install NVIDIA drivers and verify with `nvidia-smi`. |
| `uv` not found | Install with `curl -LsSf https://astral.sh/uv/install.sh \| sh`. |
| Data cache missing | Run `uv run autoresearch/data/prepare.py`. |
| OOM during training | Lower-memory mutation variants should cycle automatically; verify the GPU meets the minimum requirement. |
| Zero emissions after a long wait | Check miner logs, wallet registration, and validator availability on the subnet. |

## Validation Status

This document is structurally complete for Epic 3, but the full manual testnet walkthrough is still required once the miner is exercised on a real GPU machine and the final subnet ID is known.
