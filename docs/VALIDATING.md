# VALIDATING.md

This guide is for a validator operator who wants to run the AutoResearch validator on
testnet, plus a developer who wants to exercise the local mock runtime for regression testing.

The implementation in this repository now supports two modes:

- Testnet mode: uses real `bittensor` `Wallet`, `Subtensor`, `Metagraph`, and `Dendrite`
  surfaces when started with validator flags.
- Local mock mode: uses the built-in mock runtime for deterministic validation and testing.

## 1. Requirements

- OS: Ubuntu 22.04+ recommended for validator operation
- CPU: 4 cores and 16 GB RAM minimum
- Python: 3.10+
- Tools: `uv`, `btcli`
- Network: stable internet connection
- GPU: not required for MVP validator operation
- Optional GPU: a CUDA GPU is only needed for future replay verification work

## 2. Install

```bash
git clone https://github.com/jkbrooks/autoresearch_network.git
cd autoresearch_network
uv sync --dev --python 3.10
```

## 3. Create Wallet

```bash
btcli wallet new_coldkey --wallet.name my-validator
btcli wallet new_hotkey --wallet.name my-validator --wallet.hotkey default
```

Back up the seed phrases immediately. The validator hotkey must exist locally for startup
health checks to pass.

## 4. Get Test TAO and Register

```bash
# Obtain faucet TAO from the Bittensor Discord testnet faucet flow
btcli subnet register --netuid <NETUID> --network test \
  --wallet.name my-validator --wallet.hotkey default
```

## 5. Stake to Validator Minimum

```bash
btcli stake add --wallet.name my-validator --wallet.hotkey default \
  --amount 1100 --network test
```

Validators below the minimum stake threshold will start with a warning, but they will not
participate correctly in weight-setting consensus.

## 6. Run the Validator on Testnet

```bash
python neurons/validator.py \
  --netuid <NETUID> \
  --network test \
  --wallet.name my-validator \
  --wallet.hotkey default \
  --neuron.moving-average-alpha 0.3 \
  --logging.debug
```

Supported validator-facing flags:

- `--netuid`: subnet identifier used for metagraph and weight submission
- `--network` or `--subtensor.network`: target network, for example `test`
- `--wallet.name`: coldkey wallet name
- `--wallet.hotkey`: hotkey name used by the validator
- `--wallet.path`: wallet storage path, defaulting to `~/.bittensor/wallets`
- `--neuron.full-path`: directory where validator state is persisted
- `--neuron.moving-average-alpha`: EMA smoothing factor for score updates
- `--logging.debug`: verbose debug logging
- `--skip-health-check`: bypass startup health checks
- `--subtensor._mock`: force the built-in mock runtime instead of the real Bittensor runtime
- `--run-once`: execute a single round immediately after startup

For persistent operation, run under `tmux`, `systemd`, or another supervisor.

## 7. Understanding the Logs

Expected validator log patterns:

- `[HEALTH OK] wallet_exists: ...`
- `[HEALTH OK] network_connection: block=...`
- `[HEALTH WARN] stake_minimum: stake ... below validator minimum ...`
- `[VALIDATOR] Step 0 | Queried 3 miners | 2 responded | Best this round: ... | Global best: ...`
- `[VALIDATOR] Scores: [...]`
- `[LEADERBOARD] 1. <hotkey> | improvements: ... | experiments: ... | best_bpb: ...`

The startup banner also prints the resolved runtime mode:

- `runtime=bittensor` for the real validator path
- `runtime=mock` for the local mock path
- `runtime=injected` for unit-test injected runtimes

## 8. Monitoring

Validator state is written under `--neuron.full-path`:

- `state.npz`
- `global_best.json`
- `best_train.py`
- `submission_hashes.json`
- `miner_stats.json`

The validator auto-saves every 10 steps. You can also inspect the log output for the latest
round summary, global best, and leaderboard lines.

For testnet operation, use `btcli` to inspect registration, stake, and validator status:

```bash
btcli wallet overview --wallet.name my-validator --network test
btcli subnet show --netuid <NETUID> --network test
```

## 9. GPU and Replay Verification

The current validator does not require a GPU for normal operation. Startup health checks warn
when no CUDA GPU is present because replay verification is a future path.

If replay verification is added later, expect a dedicated GPU requirement and additional
runtime cost.

## 10. Troubleshooting

Problem: validator exits with `wallet_exists`
Solution: ensure the requested wallet and hotkey exist on disk, or verify `--wallet.path`
points to the right location.

Problem: validator exits with `network_connection`
Solution: verify the selected network endpoint is reachable and that `btcli` can talk to the
same network.

Problem: validator starts but warns about stake minimum
Solution: increase stake using `btcli stake add` until the validator is above the required
threshold.

Problem: validator warns that replay verification is disabled
Solution: this is expected on CPU-only systems today. It does not block MVP validation flow.

Problem: no miners appear to respond
Solution: confirm the metagraph contains active miner axons for the selected `netuid` and that
the network path is not running in mock mode.

## Local Mock Runtime

Use the deterministic local mock runtime for development and regression testing:

```bash
python neurons/validator.py \
  --netuid 1 \
  --network test \
  --wallet.name local-validator \
  --wallet.hotkey local-hotkey \
  --subtensor._mock \
  --skip-health-check \
  --run-once \
  --neuron.full-path .validator-state
```

This path is what the automated tests exercise. It is useful for:

- score math verification
- guard behavior
- state persistence checks
- local integration debugging

## Local Validation Commands

Focused validator tests:

```bash
.venv/bin/pytest -q --no-cov tests/test_validator_scaffold.py
.venv/bin/pytest -q --no-cov tests/test_validator_best_tracker.py
.venv/bin/pytest -q --no-cov tests/test_validator_reward.py
.venv/bin/pytest -q --no-cov tests/test_validator_guards.py
.venv/bin/pytest -q --no-cov tests/test_validator_stats.py
.venv/bin/pytest -q --no-cov tests/test_validator_forward.py
.venv/bin/pytest -q --no-cov tests/test_validator_state.py
.venv/bin/pytest -q --no-cov tests/test_integration.py
```

Full repo checks:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest -q
UV_CACHE_DIR=.uv-cache uv run ruff check .
UV_CACHE_DIR=.uv-cache uv run mypy autoresearch
```

## Manual Testnet Checklist

Use this checklist before calling the validator implementation complete on testnet:

1. Start the validator without `--subtensor._mock`.
2. Confirm the startup banner reports `runtime=bittensor`.
3. Confirm the wallet and network health checks pass.
4. Confirm the metagraph size is non-zero for the target `netuid`.
5. Confirm at least one round queries real miner axons.
6. Confirm the validator updates `global_best.json` and `best_train.py` when a better response arrives.
7. Confirm `submission_hashes.json` and `miner_stats.json` persist across restart.
8. Confirm weight submission succeeds against subtensor.
