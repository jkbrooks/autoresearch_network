---
name: autoresearch-experiment
runner: python
---

# AutoResearch Experiment Program

This program definition documents the minimum contract used by the local
experiment runner in this repository.

The default executable for experiments is `prepare.py`, which is expected to emit
key-value metrics that can be parsed by `autoresearch.experiment_runner.parse_metrics`.

## Required metric keys

- `val_bpb`
- `training_seconds`
- `peak_vram_mb`

## Optional metric keys

- `total_tokens_M`
- `num_steps`
- `throughput_toks_per_sec`
