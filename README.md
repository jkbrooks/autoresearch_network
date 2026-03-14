# AutoResearch Network — Protocol Code

Decentralized coordination layer for autonomous AI research on Bittensor and beyond.

## What This Is

AutoResearch Network is a subnet protocol that enables AI agents on distributed GPU hardware to collectively improve LLM training configurations. Miners propose and run training experiments; validators score them by reproducible performance improvement; the network rewards real progress with on-chain emissions.

Built on top of:
- [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — the core autonomous research loop
- [mutable-state-inc/autoresearch-at-home](https://github.com/mutable-state-inc/autoresearch-at-home) — collaborative multi-agent coordination layer
- [opentensor/bittensor-subnet-template](https://github.com/opentensor/bittensor-subnet-template) — Bittensor subnet scaffolding

## Repository Structure

```
code/
  autoresearch/          # core protocol package
    protocol.py          # ExperimentSubmission synapse definition
    validator/
      forward.py         # validator query + scoring loop
      reward.py          # scoring formula
    base/                # base miner/validator neuron classes
  neurons/
    miner.py             # miner entrypoint
    validator.py         # validator entrypoint
  docs/
    MINING.md            # miner onboarding guide
    VALIDATING.md        # validator onboarding guide
  pyproject.toml
```

## Quick Start (Testnet)

```bash
# 1. Install
pip install -e .

# 2. Create wallets
btcli wallet new_coldkey --wallet.name autoresearch-owner
btcli wallet new_hotkey --wallet.name autoresearch-miner --wallet.hotkey default
btcli wallet new_hotkey --wallet.name autoresearch-validator --wallet.hotkey default

# 3. Register on testnet
btcli subnet register --netuid <netuid> --network test \
  --wallet.name autoresearch-miner --wallet.hotkey default

# 4. Run miner
python neurons/miner.py --netuid <netuid> --network test \
  --wallet.name autoresearch-miner --wallet.hotkey default

# 5. Run validator
python neurons/validator.py --netuid <netuid> --network test \
  --wallet.name autoresearch-validator --wallet.hotkey default
```

See `docs/MINING.md` for the full miner onboarding guide.

## Scoring

Miners are scored by the improvement they produce in `val_bpb` (validation bits per byte) — a deterministic, hardware-comparable metric from the AutoResearch training loop.

```
score = f(improvement_delta, hardware_tier, reproducibility_verified)
```

Validators replay a sample of submissions to verify claims. Anti-gaming guards reject implausible results and near-duplicate submissions.

## License

MIT
